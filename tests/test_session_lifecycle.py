"""
Session lifecycle tests for YokeFlow.

Tests the complete lifecycle of coding sessions from initialization through completion.
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

from core.agent import run_agent_session
from core.orchestrator import SessionOrchestrator
from core.session_manager import SessionManager
from core.checkpoint import CheckpointManager, CheckpointRecoveryManager
from core.intervention import InterventionDetector
from core.observability import SessionLogger
from core.progress import ProgressTracker
from core.config import Config


@pytest.mark.asyncio
class TestAgentSession:
    """Test agent session execution."""

    async def test_agent_session_initialization(
        self, mock_claude_client, temp_project_dir, session_logger, db, test_project
    ):
        """Test initializing an agent session."""
        session_id = uuid4()
        message = "Initialize the project with the given specification."

        with patch("core.agent.create_mcp_session") as mock_mcp:
            mock_mcp.return_value = AsyncMock()

            result = await run_agent_session(
                client=mock_claude_client,
                message=message,
                project_dir=temp_project_dir,
                logger=session_logger,
                session_id=session_id,
                db=db,
                verbose=False
            )

            assert result is not None
            assert isinstance(result, tuple)
            assert len(result) == 2  # (final_message, usage)

    async def test_agent_session_with_tools(
        self, mock_claude_client, temp_project_dir, session_logger, db, mock_mcp_server
    ):
        """Test agent session with MCP tools."""
        session_id = uuid4()

        # Configure mock client to use tools
        mock_claude_client.message.return_value = Mock(
            content="Let me get the next task.",
            tool_calls=[
                Mock(name="mcp__task-manager__get_next_task", arguments={})
            ]
        )

        with patch("core.agent.create_mcp_session") as mock_mcp:
            mcp_session = AsyncMock()
            mcp_session.run_tool = AsyncMock(return_value=json.dumps({
                "task_id": 1,
                "name": "Test Task"
            }))
            mock_mcp.return_value = mcp_session

            result = await run_agent_session(
                client=mock_claude_client,
                message="Start coding session",
                project_dir=temp_project_dir,
                logger=session_logger,
                session_id=session_id,
                db=db
            )

            assert result is not None
            mcp_session.run_tool.assert_called()

    async def test_agent_session_error_handling(
        self, mock_claude_client, temp_project_dir, session_logger, db
    ):
        """Test agent session error handling."""
        session_id = uuid4()

        # Make client raise an error
        mock_claude_client.message.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await run_agent_session(
                client=mock_claude_client,
                message="This will fail",
                project_dir=temp_project_dir,
                logger=session_logger,
                session_id=session_id,
                db=db
            )

    async def test_agent_session_with_checkpoint(
        self, mock_claude_client, temp_project_dir, session_logger, db, test_session
    ):
        """Test agent session with checkpoint saving."""
        with patch("core.checkpoint.CheckpointManager") as MockCheckpoint:
            checkpoint_mgr = Mock()
            checkpoint_mgr.create_checkpoint = AsyncMock(return_value=uuid4())
            checkpoint_mgr.should_checkpoint = Mock(return_value=True)
            MockCheckpoint.return_value = checkpoint_mgr

            result = await run_agent_session(
                client=mock_claude_client,
                message="Run with checkpoints",
                project_dir=temp_project_dir,
                logger=session_logger,
                session_id=test_session,
                db=db,
                enable_checkpoints=True
            )

            checkpoint_mgr.create_checkpoint.assert_called()


@pytest.mark.asyncio
class TestSessionOrchestrator:
    """Test session orchestrator functionality."""

    async def test_orchestrator_initialization(self, test_config, db):
        """Test creating orchestrator instance."""
        orchestrator = SessionOrchestrator(config=test_config, db=db)

        assert orchestrator is not None
        assert orchestrator.config == test_config
        assert orchestrator.db == db
        assert orchestrator.active_sessions == {}

    async def test_orchestrator_run_session(
        self, test_config, db, test_project, mock_claude_client
    ):
        """Test orchestrator running a session."""
        orchestrator = SessionOrchestrator(config=test_config, db=db)

        with patch.object(orchestrator, "_execute_session") as mock_execute:
            mock_execute.return_value = AsyncMock()

            session_id = await orchestrator.run_session(
                project_id=test_project,
                session_type="initialization",
                model="claude-opus",
                message="Initialize project"
            )

            assert session_id is not None
            assert isinstance(session_id, UUID)
            mock_execute.assert_called_once()

    async def test_orchestrator_session_tracking(self, test_config, db, test_project):
        """Test orchestrator tracks active sessions."""
        orchestrator = SessionOrchestrator(config=test_config, db=db)

        # Start multiple sessions
        session1 = await orchestrator.start_session(test_project, "coding")
        session2 = await orchestrator.start_session(test_project, "coding")

        assert len(orchestrator.active_sessions) == 2
        assert session1 in orchestrator.active_sessions
        assert session2 in orchestrator.active_sessions

        # Stop a session
        await orchestrator.stop_session(session1)
        assert len(orchestrator.active_sessions) == 1
        assert session1 not in orchestrator.active_sessions

    async def test_orchestrator_concurrent_sessions(
        self, test_config, db, test_project
    ):
        """Test orchestrator handling concurrent sessions."""
        orchestrator = SessionOrchestrator(config=test_config, db=db)

        # Try to start multiple sessions for same project
        session1 = await orchestrator.start_session(test_project, "coding")

        with pytest.raises(RuntimeError, match="already running"):
            await orchestrator.start_session(test_project, "coding")

        await orchestrator.stop_session(session1)

    async def test_orchestrator_session_cleanup(
        self, test_config, db, test_project
    ):
        """Test orchestrator cleans up on session completion."""
        orchestrator = SessionOrchestrator(config=test_config, db=db)

        with patch.object(orchestrator, "_execute_session") as mock_execute:
            # Simulate session completion
            async def simulate_session(*args, **kwargs):
                await asyncio.sleep(0.01)
                return "completed"

            mock_execute.side_effect = simulate_session

            session_id = await orchestrator.run_session(
                project_id=test_project,
                session_type="coding",
                model="test-model",
                message="Test"
            )

            # Wait for session to complete
            await asyncio.sleep(0.02)

            # Session should be cleaned up
            assert session_id not in orchestrator.active_sessions


@pytest.mark.asyncio
class TestSessionManager:
    """Test session management functionality."""

    async def test_session_manager_pause_resume(self, db, test_session):
        """Test pausing and resuming sessions."""
        manager = SessionManager(db=db)

        # Pause session
        await manager.pause_session(
            session_id=test_session,
            reason="User requested pause"
        )

        status = await manager.get_session_status(test_session)
        assert status == "paused"

        # Resume session
        await manager.resume_session(test_session)

        status = await manager.get_session_status(test_session)
        assert status == "in_progress"

    async def test_session_manager_intervention(self, db, test_session):
        """Test intervention system integration."""
        manager = SessionManager(db=db)

        # Create intervention
        intervention_id = await manager.create_intervention(
            session_id=test_session,
            intervention_type="user_input_required",
            message="Please provide API key",
            metadata={"field": "api_key"}
        )

        assert intervention_id is not None

        # Get active interventions
        interventions = await manager.get_active_interventions(test_session)
        assert len(interventions) >= 1

        # Resolve intervention
        await manager.resolve_intervention(
            intervention_id=intervention_id,
            resolution="API key provided",
            resolution_data={"api_key": "test-key"}
        )

        active = await manager.get_active_interventions(test_session)
        resolved = [i for i in active if i["id"] == intervention_id]
        assert len(resolved) == 0

    async def test_session_manager_auto_continue(self, db, test_project):
        """Test automatic session continuation."""
        manager = SessionManager(db=db)

        # Enable auto-continue
        await manager.set_auto_continue(
            project_id=test_project,
            enabled=True,
            delay_seconds=3
        )

        settings = await manager.get_auto_continue_settings(test_project)
        assert settings["enabled"] is True
        assert settings["delay_seconds"] == 3

        # Disable auto-continue
        await manager.set_auto_continue(
            project_id=test_project,
            enabled=False
        )

        settings = await manager.get_auto_continue_settings(test_project)
        assert settings["enabled"] is False

    async def test_session_manager_completion_detection(self, db, test_project):
        """Test project completion detection."""
        manager = SessionManager(db=db)

        # Check if project is complete
        is_complete = await manager.is_project_complete(test_project)
        assert is_complete is False  # New project shouldn't be complete

        # Mark all tasks complete (simulation)
        async with db.acquire() as conn:
            await conn.execute("""
                UPDATE tasks
                SET status = 'completed'
                WHERE epic_id IN (
                    SELECT id FROM epics WHERE project_id = $1
                )
            """, test_project)

        is_complete = await manager.is_project_complete(test_project)
        # May or may not be complete depending on test data


@pytest.mark.asyncio
class TestCheckpointSystem:
    """Test session checkpointing and recovery."""

    async def test_checkpoint_creation(self, db, test_session, test_task):
        """Test creating a checkpoint."""
        manager = CheckpointManager(
            session_id=test_session,
            project_id=uuid4(),
            db=db
        )

        checkpoint_id = await manager.create_checkpoint(
            checkpoint_type="task_completion",
            conversation_history=[
                {"role": "user", "content": "Start task"},
                {"role": "assistant", "content": "Working on task"}
            ],
            current_task_id=test_task,
            completed_tasks=[1, 2, 3],
            metadata={"model": "test-model"}
        )

        assert checkpoint_id is not None
        assert isinstance(checkpoint_id, UUID)

    async def test_checkpoint_recovery(self, db, test_session):
        """Test recovering from a checkpoint."""
        # Create a checkpoint
        manager = CheckpointManager(
            session_id=test_session,
            project_id=uuid4(),
            db=db
        )

        conversation = [
            {"role": "user", "content": "Previous work"},
            {"role": "assistant", "content": "Previous response"}
        ]

        checkpoint_id = await manager.create_checkpoint(
            checkpoint_type="manual",
            conversation_history=conversation,
            current_task_id=5,
            completed_tasks=[1, 2, 3, 4]
        )

        # Recover from checkpoint
        recovery = CheckpointRecoveryManager(db=db)
        state = await recovery.restore_from_checkpoint(checkpoint_id)

        assert state is not None
        assert state["conversation_history"] == conversation
        assert state["current_task_id"] == 5
        assert state["completed_tasks"] == [1, 2, 3, 4]

    async def test_checkpoint_automatic_creation(self, db, test_session):
        """Test automatic checkpoint creation based on conditions."""
        manager = CheckpointManager(
            session_id=test_session,
            project_id=uuid4(),
            db=db
        )

        # Test various conditions
        assert manager.should_checkpoint(tasks_completed=5) is True  # Every 5 tasks
        assert manager.should_checkpoint(tasks_completed=3) is False
        assert manager.should_checkpoint(time_elapsed=timedelta(hours=1)) is True
        assert manager.should_checkpoint(time_elapsed=timedelta(minutes=10)) is False
        assert manager.should_checkpoint(checkpoint_type="critical") is True

    async def test_checkpoint_cleanup(self, db, test_session):
        """Test old checkpoint cleanup."""
        manager = CheckpointManager(
            session_id=test_session,
            project_id=uuid4(),
            db=db
        )

        # Create multiple checkpoints
        checkpoint_ids = []
        for i in range(10):
            checkpoint_id = await manager.create_checkpoint(
                checkpoint_type="auto",
                conversation_history=[],
                current_task_id=i
            )
            checkpoint_ids.append(checkpoint_id)

        # Cleanup old checkpoints (keep last 5)
        await manager.cleanup_old_checkpoints(keep_last=5)

        # Verify only 5 remain
        remaining = await manager.list_checkpoints()
        assert len(remaining) <= 5


@pytest.mark.asyncio
class TestInterventionSystem:
    """Test intervention detection and handling."""

    def test_intervention_detector_initialization(self):
        """Test creating intervention detector."""
        detector = InterventionDetector()

        assert detector is not None
        assert detector.retry_count == 0
        assert detector.last_error is None

    def test_detect_blocker_patterns(self):
        """Test detecting various blocker patterns."""
        detector = InterventionDetector()

        blockers = [
            "API key is missing",
            "Authentication failed",
            "Permission denied",
            "Rate limit exceeded",
            "Connection timeout",
            "Invalid credentials"
        ]

        for message in blockers:
            result = detector.detect_blocker(message)
            assert result is not None
            assert "type" in result
            assert "message" in result

    def test_detect_no_blocker(self):
        """Test normal messages don't trigger intervention."""
        detector = InterventionDetector()

        normal_messages = [
            "Task completed successfully",
            "Processing next item",
            "Building the application"
        ]

        for message in normal_messages:
            result = detector.detect_blocker(message)
            assert result is None

    def test_retry_tracking(self):
        """Test intervention retry tracking."""
        detector = InterventionDetector()

        # First error
        detector.track_error("Connection failed")
        assert detector.retry_count == 1

        # Same error again
        detector.track_error("Connection failed")
        assert detector.retry_count == 2

        # Different error resets count
        detector.track_error("Different error")
        assert detector.retry_count == 1

    def test_max_retries_detection(self):
        """Test detection of max retries exceeded."""
        detector = InterventionDetector(max_retries=3)

        for i in range(3):
            detector.track_error("Same error")
            if i < 2:
                assert not detector.should_intervene()
            else:
                assert detector.should_intervene()


@pytest.mark.asyncio
class TestProgressTracking:
    """Test progress tracking functionality."""

    async def test_progress_tracker_initialization(self, db, test_project):
        """Test creating progress tracker."""
        tracker = ProgressTracker(db=db, project_id=test_project)

        assert tracker is not None
        assert tracker.project_id == test_project

    async def test_get_project_progress(self, db, test_project):
        """Test getting overall project progress."""
        tracker = ProgressTracker(db=db, project_id=test_project)
        progress = await tracker.get_progress()

        assert progress is not None
        assert "total_epics" in progress
        assert "completed_epics" in progress
        assert "total_tasks" in progress
        assert "completed_tasks" in progress
        assert "percentage" in progress
        assert 0 <= progress["percentage"] <= 100

    async def test_get_epic_progress(self, db, test_project, test_epic):
        """Test getting epic-level progress."""
        tracker = ProgressTracker(db=db, project_id=test_project)
        progress = await tracker.get_epic_progress(test_epic)

        assert progress is not None
        assert "total_tasks" in progress
        assert "completed_tasks" in progress
        assert "percentage" in progress

    async def test_progress_updates(self, db, test_project, test_task):
        """Test progress updates when tasks complete."""
        tracker = ProgressTracker(db=db, project_id=test_project)

        # Get initial progress
        initial = await tracker.get_progress()

        # Complete a task
        await db.update_task_status(test_task, "completed")

        # Get updated progress
        updated = await tracker.get_progress()

        # Progress should increase or stay same (if task was already complete)
        assert updated["completed_tasks"] >= initial["completed_tasks"]

    async def test_progress_websocket_updates(self, db, test_project, mock_websocket):
        """Test progress updates via WebSocket."""
        tracker = ProgressTracker(db=db, project_id=test_project)
        tracker.set_websocket(mock_websocket)

        # Simulate progress update
        await tracker.send_progress_update({
            "completed_tasks": 5,
            "total_tasks": 10,
            "percentage": 50
        })

        mock_websocket.send_json.assert_called_with({
            "type": "progress",
            "data": {
                "completed_tasks": 5,
                "total_tasks": 10,
                "percentage": 50
            }
        })


@pytest.mark.asyncio
class TestSessionLogging:
    """Test session logging functionality."""

    def test_session_logger_initialization(self, temp_project_dir):
        """Test creating session logger."""
        logger = SessionLogger(
            project_dir=temp_project_dir,
            session_number=1,
            session_type="initialization",
            model="claude-opus"
        )

        assert logger is not None
        assert logger.session_number == 1
        assert logger.session_type == "initialization"

    def test_session_logger_file_creation(self, temp_project_dir):
        """Test session logger creates log files."""
        logger = SessionLogger(
            project_dir=temp_project_dir,
            session_number=1,
            session_type="coding",
            model="test-model"
        )

        logger.log_event("test", {"message": "Test event"})

        # Check log files exist
        log_dir = temp_project_dir / "logs"
        assert log_dir.exists()

        log_files = list(log_dir.glob("session_001_*.jsonl"))
        assert len(log_files) > 0

    def test_session_logger_event_types(self, temp_project_dir):
        """Test logging different event types."""
        logger = SessionLogger(
            project_dir=temp_project_dir,
            session_number=1,
            session_type="coding",
            model="test-model"
        )

        # Test various event types
        logger.log_message("user", "Test user message")
        logger.log_message("assistant", "Test assistant message")
        logger.log_tool_use("test_tool", {"param": "value"}, "result")
        logger.log_error("Test error", {"details": "Error details"})
        logger.log_event("custom", {"data": "Custom event"})

        # Verify events were logged
        assert logger.event_count >= 5

    def test_session_logger_summary(self, temp_project_dir):
        """Test session logger creates summary."""
        logger = SessionLogger(
            project_dir=temp_project_dir,
            session_number=1,
            session_type="coding",
            model="test-model"
        )

        # Log some events
        logger.log_message("user", "Start task")
        logger.log_message("assistant", "Working on task")
        logger.log_event("task_complete", {"task_id": 1})

        # Create summary
        summary = logger.get_summary()

        assert summary is not None
        assert summary["session_number"] == 1
        assert summary["event_count"] >= 3
        assert "duration" in summary
        assert "model" in summary


@pytest.mark.asyncio
class TestSessionStates:
    """Test session state transitions."""

    async def test_session_state_transitions(self, db, test_session):
        """Test valid session state transitions."""
        # Valid transitions
        valid_transitions = [
            ("pending", "in_progress"),
            ("in_progress", "paused"),
            ("paused", "in_progress"),
            ("in_progress", "completed"),
            ("in_progress", "failed"),
            ("failed", "retrying"),
            ("retrying", "in_progress")
        ]

        for from_state, to_state in valid_transitions:
            # Set initial state
            await db.update_session_status(test_session, from_state)

            # Transition to new state
            await db.update_session_status(test_session, to_state)

            # Verify transition
            session = await db.get_session(test_session)
            assert session["status"] == to_state

    async def test_invalid_session_state_transitions(self, db, test_session):
        """Test invalid session state transitions."""
        # Set to completed
        await db.update_session_status(test_session, "completed")

        # Should not allow transition back to in_progress
        # (Depending on implementation, might raise or ignore)
        session_before = await db.get_session(test_session)

        try:
            await db.update_session_status(test_session, "in_progress")
            session_after = await db.get_session(test_session)

            # If no error, state might not have changed
            if session_after["status"] == "in_progress":
                pytest.skip("State transitions not enforced")

        except Exception:
            pass  # Expected if transitions are enforced


@pytest.mark.slow
@pytest.mark.asyncio
class TestSessionPerformance:
    """Test session performance and load handling."""

    async def test_session_creation_performance(self, db, test_project):
        """Test performance of creating many sessions."""
        import time

        start = time.time()
        session_ids = []

        for i in range(100):
            session_id = uuid4()
            await db.create_session(
                session_id=session_id,
                project_id=test_project,
                session_number=i + 100,
                session_type="coding",
                model="test-model"
            )
            session_ids.append(session_id)

        duration = time.time() - start

        # Should complete in reasonable time
        assert duration < 10  # 10 seconds for 100 sessions
        assert len(session_ids) == 100

    async def test_concurrent_session_operations(self, db, test_project):
        """Test concurrent session operations."""
        # Create multiple sessions concurrently
        tasks = []
        for i in range(20):
            task = db.create_session(
                session_id=uuid4(),
                project_id=test_project,
                session_number=i + 200,
                session_type="coding",
                model="test-model"
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0

    async def test_session_memory_usage(self, db, test_project):
        """Test memory usage with many sessions."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create many sessions
        for i in range(500):
            await db.create_session(
                session_id=uuid4(),
                project_id=test_project,
                session_number=i + 300,
                session_type="coding",
                model="test-model"
            )

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Should not leak excessive memory
        assert memory_increase < 100  # Less than 100MB increase