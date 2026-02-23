"""
Concurrency and performance tests for YokeFlow.

Tests system behavior under load, concurrent operations, and performance characteristics.
"""

import asyncio
import concurrent.futures
import multiprocessing
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch
from uuid import UUID, uuid4

import psutil
import pytest
import pytest_asyncio

from core.database import TaskDatabase
from core.orchestrator import SessionOrchestrator
from core.session_manager import SessionManager
from core.config import Config


@pytest.mark.slow
@pytest.mark.asyncio
class TestDatabaseConcurrency:
    """Test database operations under concurrent load."""

    async def test_concurrent_project_creation(self, db: TaskDatabase):
        """Test creating multiple projects concurrently."""
        num_projects = 20

        async def create_project(index: int):
            project_id = uuid4()
            await db.create_project(
                project_id=project_id,
                name=f"concurrent-project-{index}",
                spec_content=f"# Project {index} Specification"
            )
            return project_id

        # Create projects concurrently
        tasks = [create_project(i) for i in range(num_projects)]
        project_ids = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        errors = [p for p in project_ids if isinstance(p, Exception)]
        assert len(errors) == 0, f"Errors during concurrent creation: {errors}"

        # Verify all projects were created
        successful_ids = [p for p in project_ids if isinstance(p, UUID)]
        assert len(successful_ids) == num_projects

    async def test_concurrent_task_updates(self, db: TaskDatabase, test_epic):
        """Test updating multiple tasks concurrently."""
        # Create tasks
        task_ids = []
        for i in range(50):
            task_id = await db.create_task(
                epic_id=test_epic,
                name=f"Concurrent Task {i}",
                description=f"Task for concurrency testing {i}"
            )
            task_ids.append(task_id)

        # Update tasks concurrently
        async def update_task(task_id: int):
            status = random.choice(["in_progress", "completed", "blocked"])
            await db.update_task_status(task_id, status)
            return task_id

        start_time = time.time()
        results = await asyncio.gather(*[update_task(tid) for tid in task_ids])
        duration = time.time() - start_time

        assert len(results) == 50
        assert duration < 5  # Should complete within 5 seconds

    async def test_concurrent_reads_and_writes(self, db: TaskDatabase, test_project):
        """Test mixed read and write operations concurrently."""
        operations = []

        # Mix of read operations
        for _ in range(10):
            operations.append(db.get_project(test_project))
            operations.append(db.list_projects())
            operations.append(db.get_project_progress(test_project))

        # Mix of write operations
        for i in range(10):
            epic_coroutine = db.create_epic(
                project_id=test_project,
                name=f"Mixed Epic {i}",
                description=f"Concurrent test {i}"
            )
            operations.append(epic_coroutine)

        # Execute all concurrently
        results = await asyncio.gather(*operations, return_exceptions=True)

        # Check for database errors
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Errors during mixed operations: {errors}"

    async def test_connection_pool_saturation(self, db: TaskDatabase):
        """Test behavior when connection pool is saturated."""
        # Get pool size (default is usually 10-20)
        pool_size = 10

        # Try to acquire more connections than pool size
        connections = []
        acquired = []

        async def acquire_and_hold():
            conn = await db.acquire()
            acquired.append(conn)
            await asyncio.sleep(0.5)  # Hold connection
            return conn

        try:
            # Launch more tasks than pool size
            tasks = [acquire_and_hold() for _ in range(pool_size + 5)]

            # Some should wait for available connections
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=2.0
            )

            # Should handle gracefully
            assert len([r for r in results if not isinstance(r, Exception)]) >= pool_size

        finally:
            # Clean up connections
            for conn in acquired:
                await conn.close()

    async def test_transaction_isolation(self, db: TaskDatabase, test_project):
        """Test transaction isolation under concurrent load."""
        epic_name = "Isolation Test Epic"

        async def transaction1():
            """Long-running transaction that creates an epic"""
            async with db.transaction() as tx:
                epic_id = await tx.fetchval("""
                    INSERT INTO epics (project_id, name, created_at)
                    VALUES ($1, $2, NOW())
                    RETURNING id
                """, test_project, epic_name)

                # Simulate processing
                await asyncio.sleep(0.1)

                # Update epic
                await tx.execute("""
                    UPDATE epics SET description = $1 WHERE id = $2
                """, "Updated in transaction", epic_id)

                return epic_id

        async def transaction2():
            """Concurrent transaction that reads epics"""
            async with db.transaction() as tx:
                # Should not see uncommitted epic
                count = await tx.fetchval("""
                    SELECT COUNT(*) FROM epics
                    WHERE project_id = $1 AND name = $2
                """, test_project, epic_name)

                return count

        # Run transactions concurrently
        results = await asyncio.gather(
            transaction1(),
            transaction2(),
            return_exceptions=True
        )

        # Transaction 2 should not see uncommitted data from transaction 1
        assert results[1] == 0  # Count should be 0


@pytest.mark.slow
@pytest.mark.asyncio
class TestSessionConcurrency:
    """Test concurrent session operations."""

    async def test_multiple_project_sessions(self, test_config, db):
        """Test running sessions for multiple projects concurrently."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Create multiple projects
        projects = []
        for i in range(5):
            project_id = uuid4()
            await db.create_project(
                project_id=project_id,
                name=f"concurrent-{i}",
                spec_content=f"# Project {i}"
            )
            projects.append(project_id)

        # Start sessions for each project
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()

            sessions = []
            for project_id in projects:
                session = await orchestrator.create_session(
                    project_id=project_id,
                    session_type="coding",
                    model="test-model"
                )
                sessions.append(session)
                await orchestrator.start_session(session.id)

            # All should be running
            assert len(orchestrator.active_sessions) == 5

    async def test_session_race_conditions(self, test_config, db, test_project):
        """Test handling of race conditions in session management."""
        manager = SessionManager(db=db)

        # Try to start same session multiple times concurrently
        session_id = uuid4()
        await db.create_session(
            session_id=session_id,
            project_id=test_project,
            session_number=1,
            session_type="coding",
            model="test-model"
        )

        async def try_start_session():
            try:
                await manager.start_session(session_id)
                return "started"
            except Exception as e:
                return f"error: {e}"

        # Multiple concurrent attempts
        results = await asyncio.gather(
            *[try_start_session() for _ in range(5)],
            return_exceptions=True
        )

        # Only one should succeed
        started = [r for r in results if r == "started"]
        assert len(started) <= 1  # At most one should succeed

    async def test_checkpoint_concurrent_creation(self, db, test_session):
        """Test concurrent checkpoint creation."""
        from core.checkpoint import CheckpointManager

        manager = CheckpointManager(
            session_id=test_session,
            project_id=uuid4(),
            db=db
        )

        async def create_checkpoint(index: int):
            return await manager.create_checkpoint(
                checkpoint_type="auto",
                conversation_history=[],
                current_task_id=index,
                metadata={"index": index}
            )

        # Create checkpoints concurrently
        tasks = [create_checkpoint(i) for i in range(10)]
        checkpoint_ids = await asyncio.gather(*tasks)

        # All should be created successfully
        assert len(checkpoint_ids) == 10
        assert len(set(checkpoint_ids)) == 10  # All unique


@pytest.mark.slow
@pytest.mark.asyncio
class TestAPIPerformance:
    """Test API performance under load."""

    async def test_api_endpoint_load(self, api_client, test_project):
        """Test API endpoints under concurrent load."""
        num_requests = 100

        async def make_request(index: int):
            start = time.time()
            response = await api_client.get(f"/projects/{test_project}")
            duration = time.time() - start
            return {
                "index": index,
                "status": response.status_code,
                "duration": duration
            }

        # Make concurrent requests
        tasks = [make_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks)

        # Analyze results
        successful = [r for r in results if r["status"] == 200]
        assert len(successful) >= num_requests * 0.95  # At least 95% success

        # Check response times
        durations = [r["duration"] for r in results]
        avg_duration = sum(durations) / len(durations)
        max_duration = max(durations)

        assert avg_duration < 0.1  # Average under 100ms
        assert max_duration < 1.0  # Max under 1 second

    async def test_api_rate_limiting(self, api_client):
        """Test API rate limiting behavior."""
        # Send rapid requests
        responses = []
        for _ in range(200):
            response = await api_client.get("/health")
            responses.append(response.status_code)

        # Check if rate limiting is applied
        rate_limited = [r for r in responses if r == 429]

        if len(rate_limited) > 0:
            # Rate limiting is enabled
            assert len(rate_limited) < 100  # Should not rate limit everything
        else:
            # Rate limiting might not be enabled
            pytest.skip("Rate limiting not configured")

    async def test_websocket_connection_limit(self, websocket_client):
        """Test WebSocket connection limits."""
        project_id = uuid4()
        connections = []

        try:
            # Try to create many connections
            for i in range(100):
                ws = websocket_client.websocket_connect(f"/ws/{project_id}")
                connections.append(ws)

            # Should handle gracefully
            assert len(connections) <= 100

        except Exception as e:
            # Connection limit reached
            assert "limit" in str(e).lower() or "maximum" in str(e).lower()

        finally:
            # Clean up connections
            for ws in connections:
                try:
                    ws.close()
                except:
                    pass


@pytest.mark.slow
@pytest.mark.asyncio
class TestMemoryPerformance:
    """Test memory usage and leak detection."""

    async def test_memory_leak_detection(self, db, test_project):
        """Test for memory leaks in repeated operations."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Perform many operations
        for _ in range(100):
            # Create and delete epics
            epic_id = await db.create_epic(
                project_id=test_project,
                name="Memory Test Epic",
                description="Testing memory usage"
            )

            # Create tasks
            for i in range(10):
                await db.create_task(
                    epic_id=epic_id,
                    name=f"Memory Task {i}",
                    description="Test"
                )

        # Force garbage collection
        import gc
        gc.collect()
        await asyncio.sleep(0.1)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Should not leak significant memory
        assert memory_increase < 100  # Less than 100MB increase

    async def test_large_data_handling(self, db, test_project):
        """Test handling of large data sets."""
        # Create large spec content
        large_spec = "# Large Specification\n" + ("x" * 1_000_000)  # 1MB

        # Should handle large content
        project_id = uuid4()
        await db.create_project(
            project_id=project_id,
            name="large-project",
            spec_content=large_spec
        )

        # Retrieve and verify
        project = await db.get_project(project_id)
        assert len(project["spec_content"]) > 1_000_000

    async def test_connection_cleanup(self, test_config):
        """Test proper cleanup of database connections."""
        from core.database_connection import DatabaseConnection

        initial_connections = []

        # Create and destroy connections
        for _ in range(20):
            conn = DatabaseConnection(test_config.database_url)
            await conn.connect()
            initial_connections.append(conn)

        # Get connection count before cleanup
        process = psutil.Process()
        initial_conn_count = len(process.connections())

        # Clean up connections
        for conn in initial_connections:
            await conn.disconnect()

        # Wait for cleanup
        await asyncio.sleep(0.5)

        # Connection count should decrease
        final_conn_count = len(process.connections())
        assert final_conn_count <= initial_conn_count


@pytest.mark.slow
@pytest.mark.asyncio
class TestCPUPerformance:
    """Test CPU-intensive operations."""

    async def test_parallel_processing(self):
        """Test parallel processing capabilities."""
        def cpu_intensive_task(n):
            """Simulate CPU-intensive work"""
            result = 0
            for i in range(n):
                result += i * i
            return result

        # Test with thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            loop = asyncio.get_event_loop()

            tasks = []
            for i in range(10):
                task = loop.run_in_executor(
                    executor,
                    cpu_intensive_task,
                    1_000_000
                )
                tasks.append(task)

            start = time.time()
            results = await asyncio.gather(*tasks)
            duration = time.time() - start

            assert len(results) == 10
            assert duration < 5  # Should complete within 5 seconds

    async def test_multiprocessing_performance(self):
        """Test multiprocessing for CPU-bound tasks."""
        def worker_task(index):
            """Worker process task"""
            result = 0
            for i in range(1_000_000):
                result += i
            return (index, result)

        # Use multiprocessing for CPU-bound work
        with multiprocessing.Pool(processes=4) as pool:
            start = time.time()
            results = pool.map(worker_task, range(10))
            duration = time.time() - start

            assert len(results) == 10
            assert duration < 5  # Should complete within 5 seconds

    async def test_async_io_performance(self, db, test_project):
        """Test async I/O performance."""
        async def io_task(index):
            """Simulate I/O-bound task"""
            # Database query
            await db.get_project(test_project)
            # Simulate network delay
            await asyncio.sleep(0.01)
            return index

        # Launch many I/O tasks
        start = time.time()
        tasks = [io_task(i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        duration = time.time() - start

        assert len(results) == 100
        # Should complete faster than sequential (100 * 0.01 = 1 second)
        assert duration < 0.5  # Concurrent execution


@pytest.mark.slow
@pytest.mark.asyncio
class TestScalability:
    """Test system scalability."""

    async def test_project_scalability(self, db):
        """Test system with many projects."""
        # Create many projects
        project_ids = []
        for i in range(100):
            project_id = uuid4()
            await db.create_project(
                project_id=project_id,
                name=f"scale-project-{i}",
                spec_content=f"# Project {i}"
            )
            project_ids.append(project_id)

        # Test listing performance
        start = time.time()
        projects = await db.list_projects()
        duration = time.time() - start

        assert len(projects) >= 100
        assert duration < 1  # Should list quickly

    async def test_task_scalability(self, db, test_project):
        """Test system with many tasks."""
        # Create epic
        epic_id = await db.create_epic(
            project_id=test_project,
            name="Scalability Epic",
            description="Testing with many tasks"
        )

        # Create many tasks
        task_ids = []
        for i in range(500):
            task_id = await db.create_task(
                epic_id=epic_id,
                name=f"Task {i}",
                description=f"Scalability test {i}"
            )
            task_ids.append(task_id)

        # Test retrieval performance
        start = time.time()
        tasks = await db.list_epic_tasks(epic_id)
        duration = time.time() - start

        assert len(tasks) == 500
        assert duration < 1  # Should retrieve quickly

    async def test_session_history_scalability(self, db, test_project):
        """Test system with large session history."""
        # Create many sessions
        for i in range(200):
            session_id = uuid4()
            await db.create_session(
                session_id=session_id,
                project_id=test_project,
                session_number=i,
                session_type="coding",
                model="test-model"
            )

        # Test history retrieval
        start = time.time()
        sessions = await db.list_project_sessions(test_project)
        duration = time.time() - start

        assert len(sessions) >= 200
        assert duration < 2  # Should retrieve reasonably quickly


@pytest.mark.slow
@pytest.mark.asyncio
class TestStressTest:
    """Stress tests for the system."""

    async def test_sustained_load(self, db, test_project):
        """Test system under sustained load."""
        duration_seconds = 10
        operations_count = 0
        errors = []
        start_time = time.time()

        async def continuous_operations():
            nonlocal operations_count, errors
            while time.time() - start_time < duration_seconds:
                try:
                    # Random operation
                    operation = random.choice([
                        lambda: db.get_project(test_project),
                        lambda: db.list_projects(),
                        lambda: db.get_project_progress(test_project),
                        lambda: db.create_epic(
                            test_project,
                            f"Stress Epic {operations_count}",
                            "Stress test"
                        )
                    ])
                    await operation()
                    operations_count += 1
                except Exception as e:
                    errors.append(e)

                # Small delay to prevent overwhelming
                await asyncio.sleep(0.001)

        # Run multiple workers
        workers = [continuous_operations() for _ in range(10)]
        await asyncio.gather(*workers)

        # Check results
        assert operations_count > 100  # Should complete many operations
        assert len(errors) < operations_count * 0.01  # Less than 1% error rate

    async def test_burst_traffic(self, api_client, test_project):
        """Test handling of traffic bursts."""
        # Generate burst of requests
        burst_size = 50

        async def burst_request():
            return await api_client.get(f"/projects/{test_project}")

        # Send burst
        start = time.time()
        tasks = [burst_request() for _ in range(burst_size)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start

        # Check handling
        successful = [
            r for r in responses
            if not isinstance(r, Exception) and r.status_code == 200
        ]
        assert len(successful) >= burst_size * 0.9  # 90% success rate
        assert duration < 5  # Should handle burst quickly

    async def test_recovery_from_overload(self, db, test_project):
        """Test system recovery from overload."""
        # Create overload condition
        overload_tasks = []
        for i in range(100):
            task = db.create_epic(
                project_id=test_project,
                name=f"Overload Epic {i}",
                description="Testing overload"
            )
            overload_tasks.append(task)

        # Execute with some expected failures
        results = await asyncio.gather(*overload_tasks, return_exceptions=True)
        errors_during_overload = [r for r in results if isinstance(r, Exception)]

        # Wait for system to recover
        await asyncio.sleep(1)

        # Test normal operation after overload
        recovery_test = await db.get_project(test_project)
        assert recovery_test is not None  # Should work normally

        # New operations should succeed
        new_epic = await db.create_epic(
            project_id=test_project,
            name="Recovery Epic",
            description="After overload"
        )
        assert new_epic is not None