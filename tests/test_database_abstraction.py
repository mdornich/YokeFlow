"""
Database abstraction layer tests for YokeFlow.

Tests the TaskDatabase class and all database operations.
"""

import asyncio
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch

from core.database import TaskDatabase
from core.database_connection import DatabaseConnection


@pytest.mark.database
@pytest.mark.asyncio
class TestDatabaseConnection:
    """Test database connection management."""

    async def test_connection_pool_creation(self, test_config):
        """Test creating database connection pool."""
        conn = DatabaseConnection(test_config.database_url)
        await conn.connect()

        assert conn.pool is not None
        assert not conn.pool._closed

        await conn.disconnect()

    async def test_connection_pool_cleanup(self, test_config):
        """Test proper connection pool cleanup."""
        conn = DatabaseConnection(test_config.database_url)
        await conn.connect()

        # Use some connections
        async with conn.pool.acquire() as connection:
            result = await connection.fetchval("SELECT 1")
            assert result == 1

        await conn.disconnect()
        assert conn.pool._closed

    async def test_connection_retry_on_failure(self, test_config):
        """Test connection retry logic."""
        with patch("asyncpg.create_pool") as mock_create:
            # Fail twice, then succeed
            mock_create.side_effect = [
                asyncpg.PostgresError("Connection failed"),
                asyncpg.PostgresError("Still failing"),
                AsyncMock(spec=asyncpg.Pool)
            ]

            conn = DatabaseConnection(test_config.database_url)
            await conn.connect(max_retries=3, initial_backoff=0.01)

            assert mock_create.call_count == 3
            assert conn.pool is not None

    async def test_connection_max_retries_exceeded(self):
        """Test failure when max retries exceeded."""
        with patch("asyncpg.create_pool") as mock_create:
            mock_create.side_effect = asyncpg.PostgresError("Always fails")

            conn = DatabaseConnection("postgresql://bad/url")
            with pytest.raises(ConnectionError, match="Could not connect"):
                await conn.connect(max_retries=2, initial_backoff=0.01)

    async def test_singleton_pattern(self, test_config):
        """Test that DatabaseConnection uses singleton pattern."""
        conn1 = DatabaseConnection(test_config.database_url)
        conn2 = DatabaseConnection(test_config.database_url)

        # Should be the same instance
        assert conn1 is conn2


@pytest.mark.database
@pytest.mark.asyncio
class TestProjectOperations:
    """Test project-related database operations."""

    async def test_create_project(self, db: TaskDatabase):
        """Test creating a new project."""
        project_id = uuid4()
        project_name = "test-create-project"
        spec_content = "# Test Specification"

        await db.create_project(
            project_id=project_id,
            name=project_name,
            spec_content=spec_content
        )

        # Verify project was created
        async with db.acquire() as conn:
            project = await conn.fetchrow(
                "SELECT * FROM projects WHERE id = $1",
                project_id
            )

        assert project is not None
        assert project["name"] == project_name
        assert project["spec_content"] == spec_content
        assert project["status"] == "initializing"

    async def test_get_project(self, db: TaskDatabase, test_project):
        """Test retrieving a project."""
        project = await db.get_project(test_project)

        assert project is not None
        assert project["id"] == test_project
        assert "name" in project
        assert "created_at" in project

    async def test_list_projects(self, db: TaskDatabase, test_project):
        """Test listing all projects."""
        projects = await db.list_projects()

        assert isinstance(projects, list)
        assert len(projects) >= 1
        assert any(p["id"] == test_project for p in projects)

    async def test_update_project_status(self, db: TaskDatabase, test_project):
        """Test updating project status."""
        await db.update_project_status(test_project, "active")

        project = await db.get_project(test_project)
        assert project["status"] == "active"

    async def test_delete_project(self, db: TaskDatabase):
        """Test deleting a project with CASCADE."""
        project_id = uuid4()
        await db.create_project(project_id, "to-delete", "# Delete me")

        # Add some related data
        async with db.acquire() as conn:
            epic_id = await conn.fetchval("""
                INSERT INTO epics (project_id, name, created_at)
                VALUES ($1, $2, NOW())
                RETURNING id
            """, project_id, "Test Epic")

        # Delete project
        await db.delete_project(project_id)

        # Verify cascade deletion
        async with db.acquire() as conn:
            epic_count = await conn.fetchval(
                "SELECT COUNT(*) FROM epics WHERE project_id = $1",
                project_id
            )
            project_count = await conn.fetchval(
                "SELECT COUNT(*) FROM projects WHERE id = $1",
                project_id
            )

        assert epic_count == 0
        assert project_count == 0

    async def test_project_exists(self, db: TaskDatabase, test_project):
        """Test checking if project exists."""
        exists = await db.project_exists(test_project)
        assert exists is True

        fake_id = uuid4()
        not_exists = await db.project_exists(fake_id)
        assert not_exists is False


@pytest.mark.database
@pytest.mark.asyncio
class TestSessionOperations:
    """Test session-related database operations."""

    async def test_create_session(self, db: TaskDatabase, test_project):
        """Test creating a new session."""
        session_id = uuid4()
        session_data = await db.create_session(
            session_id=session_id,
            project_id=test_project,
            session_number=2,
            session_type="coding",
            model="claude-sonnet-3-5"
        )

        assert session_data["id"] == session_id
        assert session_data["project_id"] == test_project
        assert session_data["status"] == "pending"
        assert session_data["session_number"] == 2

    async def test_get_session(self, db: TaskDatabase, test_session):
        """Test retrieving a session."""
        session = await db.get_session(test_session)

        assert session is not None
        assert session["id"] == test_session
        assert "status" in session
        assert "model" in session

    async def test_update_session_status(self, db: TaskDatabase, test_session):
        """Test updating session status."""
        await db.update_session_status(test_session, "completed")

        session = await db.get_session(test_session)
        assert session["status"] == "completed"

    async def test_get_latest_session(self, db: TaskDatabase, test_project):
        """Test getting the latest session for a project."""
        # Create multiple sessions
        for i in range(3):
            await db.create_session(
                session_id=uuid4(),
                project_id=test_project,
                session_number=i + 10,
                session_type="coding",
                model="test-model"
            )

        latest = await db.get_latest_session(test_project)
        assert latest is not None
        assert latest["session_number"] == 12  # Highest number

    async def test_list_project_sessions(self, db: TaskDatabase, test_project, test_session):
        """Test listing sessions for a project."""
        sessions = await db.list_project_sessions(test_project)

        assert isinstance(sessions, list)
        assert len(sessions) >= 1
        assert any(s["id"] == test_session for s in sessions)

    async def test_session_with_metrics(self, db: TaskDatabase, test_session):
        """Test storing session metrics."""
        metrics = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_cost": 0.15,
            "duration_seconds": 120
        }

        await db.update_session_metrics(test_session, metrics)

        session = await db.get_session(test_session)
        assert session["input_tokens"] == 1000
        assert session["output_tokens"] == 500
        assert session["total_cost"] == 0.15


@pytest.mark.database
@pytest.mark.asyncio
class TestEpicOperations:
    """Test epic-related database operations."""

    async def test_create_epic(self, db: TaskDatabase, test_project):
        """Test creating a new epic."""
        epic_id = await db.create_epic(
            project_id=test_project,
            name="Test Epic Creation",
            description="Testing epic creation"
        )

        assert epic_id is not None
        assert isinstance(epic_id, int)

        # Verify epic was created
        async with db.acquire() as conn:
            epic = await conn.fetchrow(
                "SELECT * FROM epics WHERE id = $1",
                epic_id
            )

        assert epic["name"] == "Test Epic Creation"
        assert epic["project_id"] == test_project

    async def test_get_epic(self, db: TaskDatabase, test_epic):
        """Test retrieving an epic."""
        epic = await db.get_epic(test_epic)

        assert epic is not None
        assert epic["id"] == test_epic
        assert "name" in epic
        assert "description" in epic

    async def test_list_project_epics(self, db: TaskDatabase, test_project, test_epic):
        """Test listing epics for a project."""
        epics = await db.list_project_epics(test_project)

        assert isinstance(epics, list)
        assert len(epics) >= 1
        assert any(e["id"] == test_epic for e in epics)

    async def test_update_epic_status(self, db: TaskDatabase, test_epic):
        """Test updating epic status."""
        await db.update_epic_status(test_epic, "completed")

        epic = await db.get_epic(test_epic)
        assert epic["status"] == "completed"

    async def test_get_epic_progress(self, db: TaskDatabase, test_epic):
        """Test getting epic progress using view."""
        # This uses the v_epic_progress view
        progress = await db.get_epic_progress(test_epic)

        assert progress is not None
        assert "total_tasks" in progress
        assert "completed_tasks" in progress
        assert "percentage_complete" in progress
        assert progress["percentage_complete"] >= 0
        assert progress["percentage_complete"] <= 100


@pytest.mark.database
@pytest.mark.asyncio
class TestTaskOperations:
    """Test task-related database operations."""

    async def test_create_task(self, db: TaskDatabase, test_epic):
        """Test creating a new task."""
        task_id = await db.create_task(
            epic_id=test_epic,
            name="Test Task Creation",
            description="Testing task creation",
            dependencies=[]
        )

        assert task_id is not None
        assert isinstance(task_id, int)

        task = await db.get_task(task_id)
        assert task["name"] == "Test Task Creation"
        assert task["epic_id"] == test_epic
        assert task["status"] == "pending"

    async def test_get_task(self, db: TaskDatabase, test_task):
        """Test retrieving a task."""
        task = await db.get_task(test_task)

        assert task is not None
        assert task["id"] == test_task
        assert "name" in task
        assert "description" in task
        assert "status" in task

    async def test_list_epic_tasks(self, db: TaskDatabase, test_epic, test_task):
        """Test listing tasks for an epic."""
        tasks = await db.list_epic_tasks(test_epic)

        assert isinstance(tasks, list)
        assert len(tasks) >= 1
        assert any(t["id"] == test_task for t in tasks)

    async def test_update_task_status(self, db: TaskDatabase, test_task):
        """Test updating task status."""
        await db.update_task_status(test_task, "in_progress")

        task = await db.get_task(test_task)
        assert task["status"] == "in_progress"

    async def test_get_next_task(self, db: TaskDatabase, test_project):
        """Test getting next available task using view."""
        # This uses the v_next_task view
        next_task = await db.get_next_task(test_project)

        if next_task:
            assert "id" in next_task
            assert "name" in next_task
            assert next_task["status"] == "pending"

    async def test_task_with_dependencies(self, db: TaskDatabase, test_epic):
        """Test creating task with dependencies."""
        # Create prerequisite task
        prereq_id = await db.create_task(
            epic_id=test_epic,
            name="Prerequisite Task",
            description="Must complete first"
        )

        # Create dependent task
        dependent_id = await db.create_task(
            epic_id=test_epic,
            name="Dependent Task",
            description="Depends on prerequisite",
            dependencies=[prereq_id]
        )

        # Verify dependency stored
        async with db.acquire() as conn:
            deps = await conn.fetchval(
                "SELECT dependencies FROM tasks WHERE id = $1",
                dependent_id
            )

        assert prereq_id in deps


@pytest.mark.database
@pytest.mark.asyncio
class TestTestOperations:
    """Test test-case related database operations."""

    async def test_create_test(self, db: TaskDatabase, test_task):
        """Test creating a test case."""
        test_id = await db.create_test(
            task_id=test_task,
            name="Test Case Creation",
            test_type="unit",
            test_code="assert 1 == 1"
        )

        assert test_id is not None
        assert isinstance(test_id, int)

        # Verify test was created
        async with db.acquire() as conn:
            test_case = await conn.fetchrow(
                "SELECT * FROM tests WHERE id = $1",
                test_id
            )

        assert test_case["name"] == "Test Case Creation"
        assert test_case["task_id"] == test_task
        assert test_case["result"] == "pending"

    async def test_update_test_result(self, db: TaskDatabase, test_task):
        """Test updating test result."""
        test_id = await db.create_test(
            task_id=test_task,
            name="Test Result Update",
            test_type="integration"
        )

        await db.update_test_result(test_id, "passed", output="All assertions passed")

        async with db.acquire() as conn:
            test_case = await conn.fetchrow(
                "SELECT * FROM tests WHERE id = $1",
                test_id
            )

        assert test_case["result"] == "passed"
        assert test_case["output"] == "All assertions passed"
        assert test_case["executed_at"] is not None

    async def test_list_task_tests(self, db: TaskDatabase, test_task):
        """Test listing tests for a task."""
        # Create some tests
        for i in range(3):
            await db.create_test(
                task_id=test_task,
                name=f"Test {i}",
                test_type="unit"
            )

        tests = await db.list_task_tests(test_task)
        assert isinstance(tests, list)
        assert len(tests) >= 3


@pytest.mark.database
@pytest.mark.asyncio
class TestProgressViews:
    """Test database views for progress tracking."""

    async def test_project_progress_view(self, db: TaskDatabase, test_project):
        """Test v_progress view."""
        async with db.acquire() as conn:
            progress = await conn.fetchrow(
                "SELECT * FROM v_progress WHERE project_id = $1",
                test_project
            )

        assert progress is not None
        assert "total_epics" in progress
        assert "completed_epics" in progress
        assert "total_tasks" in progress
        assert "completed_tasks" in progress
        assert "total_tests" in progress
        assert "passed_tests" in progress

    async def test_epic_progress_view(self, db: TaskDatabase, test_epic):
        """Test v_epic_progress view."""
        async with db.acquire() as conn:
            progress = await conn.fetchrow(
                "SELECT * FROM v_epic_progress WHERE epic_id = $1",
                test_epic
            )

        assert progress is not None
        assert "total_tasks" in progress
        assert "completed_tasks" in progress
        assert "percentage_complete" in progress


@pytest.mark.database
@pytest.mark.asyncio
class TestTransactions:
    """Test database transaction handling."""

    async def test_transaction_commit(self, db: TaskDatabase, test_project):
        """Test successful transaction commit."""
        async with db.transaction() as tx:
            epic_id = await tx.fetchval("""
                INSERT INTO epics (project_id, name, created_at)
                VALUES ($1, $2, NOW())
                RETURNING id
            """, test_project, "Transaction Test")

            task_id = await tx.fetchval("""
                INSERT INTO tasks (epic_id, name, created_at)
                VALUES ($1, $2, NOW())
                RETURNING id
            """, epic_id, "Transaction Task")

        # Verify both were committed
        epic = await db.get_epic(epic_id)
        task = await db.get_task(task_id)

        assert epic is not None
        assert task is not None

    async def test_transaction_rollback(self, db: TaskDatabase, test_project):
        """Test transaction rollback on error."""
        try:
            async with db.transaction() as tx:
                await tx.execute("""
                    INSERT INTO epics (project_id, name, created_at)
                    VALUES ($1, $2, NOW())
                """, test_project, "Rollback Test")

                # Force an error
                raise ValueError("Simulated error")

        except ValueError:
            pass

        # Verify rollback
        async with db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM epics WHERE name = $1",
                "Rollback Test"
            )

        assert count == 0

    async def test_nested_transactions(self, db: TaskDatabase, test_project):
        """Test nested transaction handling."""
        async with db.transaction() as tx1:
            epic_id = await tx1.fetchval("""
                INSERT INTO epics (project_id, name, created_at)
                VALUES ($1, $2, NOW())
                RETURNING id
            """, test_project, "Outer Transaction")

            try:
                async with db.transaction() as tx2:
                    await tx2.execute("""
                        INSERT INTO tasks (epic_id, name, created_at)
                        VALUES ($1, $2, NOW())
                    """, epic_id, "Inner Transaction")

                    # Force inner transaction to fail
                    raise ValueError("Inner failure")

            except ValueError:
                pass

            # Outer transaction should still commit
            await tx1.execute("""
                INSERT INTO tasks (epic_id, name, created_at)
                VALUES ($1, $2, NOW())
            """, epic_id, "Outer Task")

        # Verify outer committed, inner rolled back
        async with db.acquire() as conn:
            epic_exists = await conn.fetchval(
                "SELECT COUNT(*) FROM epics WHERE name = $1",
                "Outer Transaction"
            )
            inner_task = await conn.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE name = $1",
                "Inner Transaction"
            )
            outer_task = await conn.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE name = $1",
                "Outer Task"
            )

        assert epic_exists == 1
        assert inner_task == 0
        assert outer_task == 1


@pytest.mark.database
@pytest.mark.asyncio
class TestConcurrency:
    """Test concurrent database operations."""

    async def test_concurrent_reads(self, db: TaskDatabase, test_project):
        """Test multiple concurrent read operations."""
        tasks = []
        for _ in range(10):
            tasks.append(db.get_project(test_project))

        results = await asyncio.gather(*tasks)
        assert all(r is not None for r in results)
        assert all(r["id"] == test_project for r in results)

    async def test_concurrent_writes(self, db: TaskDatabase, test_project):
        """Test multiple concurrent write operations."""
        tasks = []
        for i in range(5):
            epic_coroutine = db.create_epic(
                project_id=test_project,
                name=f"Concurrent Epic {i}",
                description=f"Created concurrently {i}"
            )
            tasks.append(epic_coroutine)

        epic_ids = await asyncio.gather(*tasks)
        assert len(epic_ids) == 5
        assert len(set(epic_ids)) == 5  # All unique

    async def test_connection_pool_exhaustion(self, db: TaskDatabase):
        """Test behavior when connection pool is exhausted."""
        # Get pool size
        pool_size = db.pool._maxsize if hasattr(db.pool, '_maxsize') else 10

        # Try to acquire more connections than pool size
        connections = []
        try:
            for _ in range(pool_size + 5):
                conn = await db.acquire()
                connections.append(conn)

            # Should timeout or queue
            pytest.fail("Should have hit pool limit")

        except (asyncio.TimeoutError, asyncpg.PoolAcquireTimeoutError):
            pass  # Expected

        finally:
            # Release connections
            for conn in connections:
                await conn.close()


@pytest.mark.database
@pytest.mark.asyncio
class TestErrorHandling:
    """Test database error handling."""

    async def test_invalid_uuid(self, db: TaskDatabase):
        """Test handling of invalid UUID."""
        with pytest.raises((ValueError, asyncpg.DataError)):
            await db.get_project("not-a-uuid")

    async def test_foreign_key_violation(self, db: TaskDatabase):
        """Test foreign key constraint violation."""
        fake_project_id = uuid4()

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await db.create_epic(
                project_id=fake_project_id,  # Doesn't exist
                name="Invalid Epic",
                description="Should fail"
            )

    async def test_unique_constraint_violation(self, db: TaskDatabase):
        """Test unique constraint violation."""
        project_id = uuid4()
        await db.create_project(project_id, "unique-test", "# Test")

        with pytest.raises(asyncpg.UniqueViolationError):
            await db.create_project(project_id, "duplicate", "# Duplicate")

    async def test_check_constraint_violation(self, db: TaskDatabase, test_task):
        """Test check constraint violation."""
        with pytest.raises(asyncpg.CheckViolationError):
            async with db.acquire() as conn:
                await conn.execute("""
                    UPDATE tasks
                    SET status = 'invalid_status'
                    WHERE id = $1
                """, test_task)

    async def test_null_constraint_violation(self, db: TaskDatabase):
        """Test NOT NULL constraint violation."""
        with pytest.raises(asyncpg.NotNullViolationError):
            async with db.acquire() as conn:
                await conn.execute("""
                    INSERT INTO projects (id, name)
                    VALUES ($1, NULL)
                """, uuid4())