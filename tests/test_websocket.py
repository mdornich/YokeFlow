"""
WebSocket tests for YokeFlow.

Tests real-time WebSocket communication for progress updates and live monitoring.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketState

from api.main import app, ws_manager


@pytest.fixture
def websocket_client():
    """Create a test WebSocket client."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_websocket_connection():
    """Create a mock WebSocket connection."""
    ws = Mock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    ws.client_state = WebSocketState.CONNECTED
    ws.application_state = WebSocketState.CONNECTED
    return ws


@pytest.mark.asyncio
class TestWebSocketConnection:
    """Test WebSocket connection establishment and lifecycle."""

    async def test_websocket_connect(self, websocket_client, test_project):
        """Test establishing WebSocket connection."""
        with websocket_client.websocket_connect(f"/ws/{test_project}") as websocket:
            # Send initial message
            websocket.send_json({"type": "subscribe", "project_id": str(test_project)})

            # Should receive acknowledgment
            data = websocket.receive_json()
            assert data["type"] in ["subscribed", "connection_established"]

    async def test_websocket_authentication(self, websocket_client):
        """Test WebSocket authentication."""
        # Try to connect without valid project ID
        with pytest.raises(WebSocketDisconnect):
            with websocket_client.websocket_connect("/ws/invalid-id") as websocket:
                pass

    async def test_websocket_disconnect(self, mock_websocket_connection):
        """Test WebSocket disconnection handling."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Connect
        await manager.connect(mock_websocket_connection, project_id)
        assert mock_websocket_connection in manager.active_connections.get(project_id, [])

        # Disconnect
        await manager.disconnect(mock_websocket_connection, project_id)
        assert mock_websocket_connection not in manager.active_connections.get(project_id, [])

    async def test_multiple_connections(self, mock_websocket_connection):
        """Test multiple WebSocket connections for same project."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Create multiple connections
        connections = [mock_websocket_connection]
        for _ in range(3):
            ws = Mock(spec=WebSocket)
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock()
            connections.append(ws)

        # Connect all
        for ws in connections:
            await manager.connect(ws, project_id)

        assert len(manager.active_connections[project_id]) == 4

    async def test_connection_cleanup_on_error(self, mock_websocket_connection):
        """Test connection cleanup on error."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Connect
        await manager.connect(mock_websocket_connection, project_id)

        # Simulate error in send
        mock_websocket_connection.send_json.side_effect = WebSocketDisconnect()

        # Try to send message
        await manager.send_to_project(project_id, {"type": "test"})

        # Connection should be cleaned up
        assert mock_websocket_connection not in manager.active_connections.get(project_id, [])


@pytest.mark.asyncio
class TestProgressUpdates:
    """Test real-time progress updates via WebSocket."""

    async def test_send_progress_update(self, mock_websocket_connection):
        """Test sending progress updates."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        await manager.connect(mock_websocket_connection, project_id)

        # Send progress update
        progress_data = {
            "type": "progress",
            "data": {
                "total_tasks": 100,
                "completed_tasks": 50,
                "percentage": 50.0
            }
        }

        await manager.send_progress_update(project_id, progress_data)

        mock_websocket_connection.send_json.assert_called_with(progress_data)

    async def test_broadcast_to_all_connections(self, mock_websocket_connection):
        """Test broadcasting to all connections for a project."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Connect multiple clients
        connections = [mock_websocket_connection]
        for _ in range(2):
            ws = Mock(spec=WebSocket)
            ws.send_json = AsyncMock()
            connections.append(ws)
            await manager.connect(ws, project_id)

        # Broadcast message
        message = {"type": "broadcast", "data": "test"}
        await manager.broadcast_to_project(project_id, message)

        # All connections should receive message
        for ws in connections:
            ws.send_json.assert_called_with(message)

    async def test_task_completion_update(self, mock_websocket_connection, db, test_project, test_task):
        """Test task completion triggers WebSocket update."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        # Complete a task
        await db.update_task_status(test_task, "completed")

        # Trigger update
        await manager.send_task_update(test_project, test_task, "completed")

        # Should receive task update
        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "task_update"
        assert call_args["task_id"] == test_task
        assert call_args["status"] == "completed"

    async def test_epic_completion_update(self, mock_websocket_connection, db, test_project, test_epic):
        """Test epic completion triggers WebSocket update."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        # Send epic update
        await manager.send_epic_update(test_project, test_epic, "completed")

        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "epic_update"
        assert call_args["epic_id"] == test_epic
        assert call_args["status"] == "completed"


@pytest.mark.asyncio
class TestSessionUpdates:
    """Test session-related WebSocket updates."""

    async def test_session_start_notification(self, mock_websocket_connection, test_project):
        """Test notification when session starts."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        session_id = uuid4()
        await manager.send_session_update(test_project, session_id, "started", {
            "session_number": 1,
            "session_type": "coding",
            "model": "claude-sonnet"
        })

        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "session_update"
        assert call_args["session_id"] == str(session_id)
        assert call_args["status"] == "started"

    async def test_session_log_streaming(self, mock_websocket_connection, test_project):
        """Test streaming session logs."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        # Stream log entries
        log_entries = [
            {"timestamp": "2024-01-01T00:00:00", "level": "INFO", "message": "Starting task"},
            {"timestamp": "2024-01-01T00:00:01", "level": "INFO", "message": "Task completed"}
        ]

        for entry in log_entries:
            await manager.stream_log_entry(test_project, entry)

        assert mock_websocket_connection.send_json.call_count == len(log_entries)

    async def test_session_error_notification(self, mock_websocket_connection, test_project):
        """Test error notifications via WebSocket."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        error_data = {
            "error_type": "APIError",
            "message": "Rate limit exceeded",
            "details": {"retry_after": 60}
        }

        await manager.send_error_notification(test_project, error_data)

        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert call_args["error"]["message"] == "Rate limit exceeded"

    async def test_session_completion_notification(self, mock_websocket_connection, test_project):
        """Test notification when session completes."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        completion_data = {
            "session_id": str(uuid4()),
            "status": "completed",
            "summary": {
                "tasks_completed": 10,
                "tests_passed": 15,
                "duration_seconds": 300
            }
        }

        await manager.send_session_completion(test_project, completion_data)

        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "session_completed"
        assert call_args["summary"]["tasks_completed"] == 10


@pytest.mark.asyncio
class TestInterventionUpdates:
    """Test intervention-related WebSocket updates."""

    async def test_intervention_required_notification(self, mock_websocket_connection, test_project):
        """Test notification when intervention is required."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        intervention_data = {
            "intervention_id": str(uuid4()),
            "type": "user_input_required",
            "message": "Please provide API key",
            "field": "api_key"
        }

        await manager.send_intervention_required(test_project, intervention_data)

        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "intervention_required"
        assert call_args["intervention"]["message"] == "Please provide API key"

    async def test_intervention_resolved_notification(self, mock_websocket_connection, test_project):
        """Test notification when intervention is resolved."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket_connection, test_project)

        resolution_data = {
            "intervention_id": str(uuid4()),
            "resolved_by": "user",
            "resolution": "API key provided"
        }

        await manager.send_intervention_resolved(test_project, resolution_data)

        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "intervention_resolved"
        assert call_args["resolution"]["resolution"] == "API key provided"


@pytest.mark.asyncio
class TestMessageHandling:
    """Test WebSocket message handling."""

    async def test_ping_pong(self, mock_websocket_connection):
        """Test ping-pong keep-alive."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()
        await manager.connect(mock_websocket_connection, project_id)

        # Simulate receiving ping
        mock_websocket_connection.receive_json.return_value = {"type": "ping"}

        # Handle message
        await manager.handle_message(mock_websocket_connection, project_id)

        # Should send pong
        mock_websocket_connection.send_json.assert_called_with({"type": "pong"})

    async def test_subscribe_unsubscribe(self, mock_websocket_connection):
        """Test subscription management."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()
        await manager.connect(mock_websocket_connection, project_id)

        # Subscribe to specific events
        mock_websocket_connection.receive_json.return_value = {
            "type": "subscribe",
            "events": ["progress", "errors"]
        }

        await manager.handle_message(mock_websocket_connection, project_id)

        # Verify subscription
        assert manager.is_subscribed(mock_websocket_connection, "progress")
        assert manager.is_subscribed(mock_websocket_connection, "errors")
        assert not manager.is_subscribed(mock_websocket_connection, "logs")

        # Unsubscribe
        mock_websocket_connection.receive_json.return_value = {
            "type": "unsubscribe",
            "events": ["errors"]
        }

        await manager.handle_message(mock_websocket_connection, project_id)

        assert manager.is_subscribed(mock_websocket_connection, "progress")
        assert not manager.is_subscribed(mock_websocket_connection, "errors")

    async def test_invalid_message_handling(self, mock_websocket_connection):
        """Test handling of invalid messages."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()
        await manager.connect(mock_websocket_connection, project_id)

        # Invalid message format
        mock_websocket_connection.receive_json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        # Should handle gracefully
        await manager.handle_message(mock_websocket_connection, project_id)

        # Should send error message
        call_args = mock_websocket_connection.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert "Invalid message format" in call_args["message"]

    async def test_rate_limiting(self, mock_websocket_connection):
        """Test WebSocket message rate limiting."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager(rate_limit=10)  # 10 messages per second
        project_id = uuid4()
        await manager.connect(mock_websocket_connection, project_id)

        # Send many messages quickly
        for _ in range(15):
            await manager.send_to_project(project_id, {"type": "test"})

        # Some messages should be rate limited
        # (Implementation depends on rate limiting strategy)
        assert mock_websocket_connection.send_json.call_count <= 11  # Allow 1 extra


@pytest.mark.asyncio
class TestReconnection:
    """Test WebSocket reconnection handling."""

    async def test_reconnect_after_disconnect(self, mock_websocket_connection):
        """Test client can reconnect after disconnect."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Initial connection
        await manager.connect(mock_websocket_connection, project_id)
        client_id = manager.get_client_id(mock_websocket_connection)

        # Disconnect
        await manager.disconnect(mock_websocket_connection, project_id)

        # Reconnect with same client ID
        new_ws = Mock(spec=WebSocket)
        new_ws.accept = AsyncMock()
        new_ws.send_json = AsyncMock()

        await manager.reconnect(new_ws, project_id, client_id)

        assert new_ws in manager.active_connections[project_id]

    async def test_restore_subscriptions_on_reconnect(self, mock_websocket_connection):
        """Test subscription restoration on reconnect."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Initial connection with subscriptions
        await manager.connect(mock_websocket_connection, project_id)
        await manager.subscribe(mock_websocket_connection, ["progress", "errors"])
        client_id = manager.get_client_id(mock_websocket_connection)

        # Disconnect
        await manager.disconnect(mock_websocket_connection, project_id)

        # Reconnect
        new_ws = Mock(spec=WebSocket)
        new_ws.accept = AsyncMock()
        new_ws.send_json = AsyncMock()

        await manager.reconnect(new_ws, project_id, client_id)

        # Subscriptions should be restored
        assert manager.is_subscribed(new_ws, "progress")
        assert manager.is_subscribed(new_ws, "errors")


@pytest.mark.asyncio
class TestBroadcasting:
    """Test message broadcasting to multiple clients."""

    async def test_selective_broadcast(self):
        """Test broadcasting to specific event subscribers only."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Create connections with different subscriptions
        ws1 = Mock(spec=WebSocket)
        ws1.send_json = AsyncMock()
        await manager.connect(ws1, project_id)
        await manager.subscribe(ws1, ["progress"])

        ws2 = Mock(spec=WebSocket)
        ws2.send_json = AsyncMock()
        await manager.connect(ws2, project_id)
        await manager.subscribe(ws2, ["errors"])

        ws3 = Mock(spec=WebSocket)
        ws3.send_json = AsyncMock()
        await manager.connect(ws3, project_id)
        await manager.subscribe(ws3, ["progress", "errors"])

        # Broadcast progress update
        await manager.broadcast_event(project_id, "progress", {"data": "progress"})

        # Only ws1 and ws3 should receive
        ws1.send_json.assert_called()
        ws2.send_json.assert_not_called()
        ws3.send_json.assert_called()

    async def test_broadcast_to_multiple_projects(self):
        """Test broadcasting doesn't leak between projects."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project1 = uuid4()
        project2 = uuid4()

        # Connections for different projects
        ws1 = Mock(spec=WebSocket)
        ws1.send_json = AsyncMock()
        await manager.connect(ws1, project1)

        ws2 = Mock(spec=WebSocket)
        ws2.send_json = AsyncMock()
        await manager.connect(ws2, project2)

        # Broadcast to project1 only
        await manager.send_to_project(project1, {"type": "test"})

        # Only ws1 should receive
        ws1.send_json.assert_called()
        ws2.send_json.assert_not_called()


@pytest.mark.asyncio
class TestPerformance:
    """Test WebSocket performance."""

    async def test_many_connections(self):
        """Test handling many concurrent connections."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()

        # Create many connections
        connections = []
        for i in range(100):
            ws = Mock(spec=WebSocket)
            ws.send_json = AsyncMock()
            ws.accept = AsyncMock()
            connections.append(ws)
            await manager.connect(ws, project_id)

        assert len(manager.active_connections[project_id]) == 100

        # Broadcast to all
        import time
        start = time.time()
        await manager.broadcast_to_project(project_id, {"type": "test"})
        duration = time.time() - start

        # Should complete quickly
        assert duration < 1  # Less than 1 second for 100 connections

    async def test_high_message_throughput(self, mock_websocket_connection):
        """Test handling high message throughput."""
        from api.websocket import ConnectionManager

        manager = ConnectionManager()
        project_id = uuid4()
        await manager.connect(mock_websocket_connection, project_id)

        # Send many messages rapidly
        import time
        start = time.time()

        for i in range(1000):
            await manager.send_to_project(project_id, {
                "type": "update",
                "index": i
            })

        duration = time.time() - start

        # Should handle 1000 messages quickly
        assert duration < 2  # Less than 2 seconds

    async def test_connection_memory_usage(self):
        """Test memory usage with many connections."""
        from api.websocket import ConnectionManager
        import psutil
        import os

        manager = ConnectionManager()
        project_id = uuid4()

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create many connections
        connections = []
        for i in range(500):
            ws = Mock(spec=WebSocket)
            ws.send_json = AsyncMock()
            connections.append(ws)
            await manager.connect(ws, project_id)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Should not use excessive memory
        assert memory_increase < 50  # Less than 50MB for 500 connections