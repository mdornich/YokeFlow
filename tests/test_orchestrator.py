"""
Orchestrator tests for YokeFlow.

Tests the SessionOrchestrator class that manages session lifecycle and coordination.
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from core.orchestrator import SessionOrchestrator, SessionState
from core.config import Config
from core.database import TaskDatabase


@pytest.mark.asyncio
class TestOrchestratorInitialization:
    """Test orchestrator initialization and configuration."""

    def test_orchestrator_creation(self, test_config):
        """Test creating orchestrator instance."""
        with patch("core.orchestrator.TaskDatabase") as MockDB:
            mock_db = Mock(spec=TaskDatabase)
            MockDB.return_value = mock_db

            orchestrator = SessionOrchestrator(
                config=test_config,
                project_dir=Path("/test/project")
            )

            assert orchestrator is not None
            assert orchestrator.config == test_config
            assert orchestrator.project_dir == Path("/test/project")
            assert orchestrator.active_sessions == {}
            assert orchestrator.session_queue == []

    def test_orchestrator_with_custom_config(self):
        """Test orchestrator with custom configuration."""
        config = Config()
        config.max_concurrent_sessions = 3
        config.session_timeout = 3600
        config.auto_continue_delay = 5

        with patch("core.orchestrator.TaskDatabase") as MockDB:
            orchestrator = SessionOrchestrator(
                config=config,
                project_dir=Path("/test")
            )

            assert orchestrator.max_concurrent == 3
            assert orchestrator.session_timeout == 3600
            assert orchestrator.auto_continue_delay == 5

    async def test_orchestrator_database_connection(self, test_config, db):
        """Test orchestrator establishes database connection."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Test database is accessible
        await orchestrator.db.execute("SELECT 1")
        assert orchestrator.db is not None


@pytest.mark.asyncio
class TestSessionLifecycle:
    """Test session lifecycle management."""

    async def test_create_session(self, test_config, db, test_project):
        """Test creating a new session."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="initialization",
            model="claude-opus"
        )

        assert session is not None
        assert session.id is not None
        assert session.project_id == test_project
        assert session.session_type == "initialization"
        assert session.state == SessionState.PENDING

    async def test_start_session(self, test_config, db, test_project):
        """Test starting a session."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="claude-sonnet"
        )

        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()

            await orchestrator.start_session(session.id)

            assert session.id in orchestrator.active_sessions
            assert orchestrator.active_sessions[session.id].state == SessionState.RUNNING
            mock_run.assert_called_once()

    async def test_stop_session(self, test_config, db, test_project):
        """Test stopping a running session."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        # Start session
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()
            await orchestrator.start_session(session.id)

        # Stop session
        await orchestrator.stop_session(session.id)

        assert session.id not in orchestrator.active_sessions

        # Verify database updated
        db_session = await db.get_session(session.id)
        assert db_session["status"] in ["stopped", "cancelled", "completed"]

    async def test_pause_resume_session(self, test_config, db, test_project):
        """Test pausing and resuming a session."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        # Start session
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()
            await orchestrator.start_session(session.id)

        # Pause session
        await orchestrator.pause_session(session.id, reason="User requested")

        assert orchestrator.active_sessions[session.id].state == SessionState.PAUSED

        # Resume session
        await orchestrator.resume_session(session.id)

        assert orchestrator.active_sessions[session.id].state == SessionState.RUNNING

    async def test_session_completion(self, test_config, db, test_project):
        """Test session completion handling."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        with patch.object(orchestrator, "_run_session") as mock_run:
            # Simulate session completion
            async def complete_session(*args, **kwargs):
                await asyncio.sleep(0.01)
                await orchestrator._mark_session_complete(session.id)

            mock_run.side_effect = complete_session

            await orchestrator.start_session(session.id)
            await asyncio.sleep(0.02)  # Wait for completion

            assert session.id not in orchestrator.active_sessions

            db_session = await db.get_session(session.id)
            assert db_session["status"] == "completed"


@pytest.mark.asyncio
class TestSessionQueue:
    """Test session queue management."""

    async def test_queue_session(self, test_config, db, test_project):
        """Test queueing sessions when at max capacity."""
        config = Config()
        config.max_concurrent_sessions = 2

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        # Create and start max sessions
        sessions = []
        for i in range(2):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            sessions.append(session)

            with patch.object(orchestrator, "_run_session") as mock_run:
                mock_run.return_value = AsyncMock()
                await orchestrator.start_session(session.id)

        # Try to start another session - should queue
        queued_session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        await orchestrator.queue_session(queued_session.id)

        assert queued_session.id in orchestrator.session_queue
        assert len(orchestrator.session_queue) == 1

    async def test_process_queue_on_completion(self, test_config, db, test_project):
        """Test queue processing when a session completes."""
        config = Config()
        config.max_concurrent_sessions = 1

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        # Start first session
        session1 = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()
            await orchestrator.start_session(session1.id)

        # Queue second session
        session2 = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )
        await orchestrator.queue_session(session2.id)

        # Complete first session
        await orchestrator.stop_session(session1.id)

        # Trigger queue processing
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()
            await orchestrator._process_queue()

            # Second session should now be running
            assert session2.id in orchestrator.active_sessions
            assert len(orchestrator.session_queue) == 0

    async def test_queue_priority(self, test_config, db, test_project):
        """Test session queue priority handling."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Queue multiple sessions with different priorities
        low_priority = await orchestrator.create_session(
            project_id=test_project,
            session_type="review",
            model="test-model",
            priority=10
        )

        high_priority = await orchestrator.create_session(
            project_id=test_project,
            session_type="initialization",
            model="test-model",
            priority=1
        )

        await orchestrator.queue_session(low_priority.id)
        await orchestrator.queue_session(high_priority.id)

        # High priority should be first
        next_session = orchestrator._get_next_queued_session()
        assert next_session == high_priority.id


@pytest.mark.asyncio
class TestAutoContinue:
    """Test automatic session continuation."""

    async def test_auto_continue_enabled(self, test_config, db, test_project):
        """Test auto-continue when enabled."""
        config = Config()
        config.auto_continue_enabled = True
        config.auto_continue_delay = 0.1  # 100ms for testing

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        with patch.object(orchestrator, "_should_continue") as mock_should:
            mock_should.return_value = True

            with patch.object(orchestrator, "create_session") as mock_create:
                mock_session = Mock()
                mock_session.id = uuid4()
                mock_create.return_value = mock_session

                with patch.object(orchestrator, "start_session") as mock_start:
                    mock_start.return_value = AsyncMock()

                    # Complete a session
                    session = await orchestrator.create_session(
                        project_id=test_project,
                        session_type="coding",
                        model="test-model"
                    )

                    await orchestrator._trigger_auto_continue(
                        project_id=test_project,
                        last_session_type="coding"
                    )

                    await asyncio.sleep(0.2)  # Wait for delay

                    mock_create.assert_called()
                    mock_start.assert_called()

    async def test_auto_continue_disabled(self, test_config, db, test_project):
        """Test auto-continue when disabled."""
        config = Config()
        config.auto_continue_enabled = False

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        with patch.object(orchestrator, "create_session") as mock_create:
            await orchestrator._trigger_auto_continue(
                project_id=test_project,
                last_session_type="coding"
            )

            mock_create.assert_not_called()

    async def test_auto_continue_max_iterations(self, test_config, db, test_project):
        """Test auto-continue respects max iterations."""
        config = Config()
        config.auto_continue_enabled = True
        config.max_iterations = 5

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        # Simulate 5 sessions already completed
        async with db.acquire() as conn:
            for i in range(5):
                await conn.execute("""
                    INSERT INTO sessions (
                        id, project_id, session_number,
                        status, started_at, model, session_type
                    )
                    VALUES ($1, $2, $3, $4, NOW(), $5, $6)
                """, uuid4(), test_project, i + 1, "completed", "test", "coding")

        should_continue = await orchestrator._should_continue(test_project)
        assert should_continue is False


@pytest.mark.asyncio
class TestConcurrency:
    """Test concurrent session handling."""

    async def test_concurrent_session_limit(self, test_config, db, test_project):
        """Test enforcing concurrent session limit."""
        config = Config()
        config.max_concurrent_sessions = 2

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        sessions = []
        for i in range(3):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            sessions.append(session)

        # Start first two sessions
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()

            for session in sessions[:2]:
                await orchestrator.start_session(session.id)

            assert len(orchestrator.active_sessions) == 2

            # Third session should fail or queue
            with pytest.raises(RuntimeError, match="Maximum concurrent"):
                await orchestrator.start_session(sessions[2].id)

    async def test_different_project_concurrency(self, test_config, db):
        """Test concurrent sessions for different projects."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Create different projects
        project1 = uuid4()
        project2 = uuid4()

        await db.create_project(project1, "project1", "# Spec 1")
        await db.create_project(project2, "project2", "# Spec 2")

        # Create sessions for different projects
        session1 = await orchestrator.create_session(
            project_id=project1,
            session_type="coding",
            model="test-model"
        )

        session2 = await orchestrator.create_session(
            project_id=project2,
            session_type="coding",
            model="test-model"
        )

        # Both should be able to run concurrently
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()

            await orchestrator.start_session(session1.id)
            await orchestrator.start_session(session2.id)

            assert len(orchestrator.active_sessions) == 2

    async def test_session_isolation(self, test_config, db, test_project):
        """Test sessions are isolated from each other."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        sessions = []
        for i in range(2):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            sessions.append(session)

        # Start sessions with different contexts
        with patch.object(orchestrator, "_run_session") as mock_run:
            contexts = []

            async def track_context(session_id, context):
                contexts.append(context)

            mock_run.side_effect = track_context

            for i, session in enumerate(sessions):
                await orchestrator.start_session(
                    session.id,
                    context={"index": i}
                )

            # Verify each session got its own context
            assert len(contexts) == 2
            assert contexts[0]["index"] == 0
            assert contexts[1]["index"] == 1


@pytest.mark.asyncio
class TestErrorHandling:
    """Test orchestrator error handling."""

    async def test_session_failure_handling(self, test_config, db, test_project):
        """Test handling of session failures."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.side_effect = Exception("Session crashed")

            with pytest.raises(Exception):
                await orchestrator.start_session(session.id)

            # Session should be marked as failed
            db_session = await db.get_session(session.id)
            assert db_session["status"] == "failed"

    async def test_session_timeout(self, test_config, db, test_project):
        """Test session timeout handling."""
        config = Config()
        config.session_timeout = 0.1  # 100ms timeout for testing

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        with patch.object(orchestrator, "_run_session") as mock_run:
            # Simulate long-running session
            async def long_running(*args, **kwargs):
                await asyncio.sleep(1)  # Longer than timeout

            mock_run.side_effect = long_running

            with pytest.raises(asyncio.TimeoutError):
                await orchestrator.start_session_with_timeout(session.id)

    async def test_recovery_after_failure(self, test_config, db, test_project):
        """Test session recovery after failure."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        # First attempt fails
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.side_effect = Exception("First attempt failed")

            with pytest.raises(Exception):
                await orchestrator.start_session(session.id)

        # Recovery attempt
        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()

            await orchestrator.retry_session(session.id)

            # Should be running again
            assert session.id in orchestrator.active_sessions
            assert orchestrator.active_sessions[session.id].state == SessionState.RUNNING


@pytest.mark.asyncio
class TestMonitoring:
    """Test session monitoring and metrics."""

    async def test_get_active_sessions(self, test_config, db, test_project):
        """Test retrieving active sessions."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Start multiple sessions
        sessions = []
        for i in range(3):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            sessions.append(session)

            with patch.object(orchestrator, "_run_session") as mock_run:
                mock_run.return_value = AsyncMock()
                await orchestrator.start_session(session.id)

        active = orchestrator.get_active_sessions()
        assert len(active) == 3
        assert all(s.id in active for s in sessions)

    async def test_get_session_metrics(self, test_config, db, test_project):
        """Test collecting session metrics."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        # Simulate session with metrics
        metrics = {
            "start_time": datetime.now(),
            "tasks_completed": 5,
            "tokens_used": 1000,
            "errors_encountered": 2
        }

        await orchestrator.update_session_metrics(session.id, metrics)

        retrieved = await orchestrator.get_session_metrics(session.id)
        assert retrieved["tasks_completed"] == 5
        assert retrieved["tokens_used"] == 1000

    async def test_session_history(self, test_config, db, test_project):
        """Test retrieving session history."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Create multiple sessions
        for i in range(5):
            await orchestrator.create_session(
                project_id=test_project,
                session_type="coding" if i % 2 == 0 else "review",
                model="test-model"
            )

        history = await orchestrator.get_project_session_history(test_project)
        assert len(history) >= 5

        # Verify history is ordered by creation time
        times = [s["created_at"] for s in history]
        assert times == sorted(times, reverse=True)  # Most recent first


@pytest.mark.asyncio
class TestCleanup:
    """Test orchestrator cleanup operations."""

    async def test_cleanup_on_shutdown(self, test_config, db, test_project):
        """Test cleanup when orchestrator shuts down."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Start some sessions
        sessions = []
        for i in range(2):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            sessions.append(session)

            with patch.object(orchestrator, "_run_session") as mock_run:
                mock_run.return_value = AsyncMock()
                await orchestrator.start_session(session.id)

        # Shutdown orchestrator
        await orchestrator.shutdown()

        # All sessions should be stopped
        assert len(orchestrator.active_sessions) == 0

        # Database should reflect stopped status
        for session in sessions:
            db_session = await db.get_session(session.id)
            assert db_session["status"] in ["stopped", "cancelled"]

    async def test_cleanup_stale_sessions(self, test_config, db, test_project):
        """Test cleaning up stale/stuck sessions."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        # Create a stale session (marked as running but not actually active)
        stale_session = uuid4()
        await db.create_session(
            session_id=stale_session,
            project_id=test_project,
            session_number=99,
            session_type="coding",
            model="test-model"
        )
        await db.update_session_status(stale_session, "in_progress")

        # Run cleanup
        await orchestrator.cleanup_stale_sessions()

        # Stale session should be marked as failed or stopped
        db_session = await db.get_session(stale_session)
        assert db_session["status"] in ["failed", "stopped"]

    async def test_resource_cleanup(self, test_config, db, test_project):
        """Test cleanup of session resources."""
        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        session = await orchestrator.create_session(
            project_id=test_project,
            session_type="coding",
            model="test-model"
        )

        # Allocate some resources (mocked)
        resources = {
            "docker_container": Mock(),
            "mcp_session": AsyncMock(),
            "log_file": Mock()
        }

        orchestrator.session_resources[session.id] = resources

        # Cleanup session
        await orchestrator.cleanup_session_resources(session.id)

        # Resources should be cleaned up
        assert session.id not in orchestrator.session_resources


@pytest.mark.slow
@pytest.mark.asyncio
class TestOrchestratorPerformance:
    """Test orchestrator performance."""

    async def test_many_sessions_performance(self, test_config, db, test_project):
        """Test performance with many sessions."""
        import time

        orchestrator = SessionOrchestrator(
            config=test_config,
            project_dir=Path("/test"),
            db=db
        )

        start = time.time()

        # Create many sessions
        sessions = []
        for i in range(100):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            sessions.append(session)

        duration = time.time() - start

        # Should complete quickly
        assert duration < 5  # Less than 5 seconds for 100 sessions
        assert len(sessions) == 100

    async def test_queue_performance(self, test_config, db, test_project):
        """Test queue performance with many pending sessions."""
        config = Config()
        config.max_concurrent_sessions = 2

        orchestrator = SessionOrchestrator(
            config=config,
            project_dir=Path("/test"),
            db=db
        )

        # Queue many sessions
        for i in range(50):
            session = await orchestrator.create_session(
                project_id=test_project,
                session_type="coding",
                model="test-model"
            )
            await orchestrator.queue_session(session.id)

        assert len(orchestrator.session_queue) == 50

        # Process queue should be efficient
        import time
        start = time.time()

        with patch.object(orchestrator, "_run_session") as mock_run:
            mock_run.return_value = AsyncMock()

            # Process entire queue
            while orchestrator.session_queue:
                await orchestrator._process_queue()
                await asyncio.sleep(0.001)  # Small delay

        duration = time.time() - start
        assert duration < 2  # Should process quickly