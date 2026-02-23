"""
API integration tests for YokeFlow.

Tests all REST API endpoints and WebSocket functionality.
"""

import json
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from fastapi import status


@pytest.mark.api
@pytest.mark.asyncio
class TestProjectEndpoints:
    """Test project-related API endpoints."""

    async def test_create_project_success(self, api_client: AsyncClient, sample_project_data: Dict[str, Any]):
        """Test successful project creation."""
        response = await api_client.post("/projects", json=sample_project_data)

        assert response.status_code == status.HTTP_201_CREATED
        project = response.json()
        assert project["name"] == sample_project_data["name"]
        assert project["spec_content"] == sample_project_data["spec_content"]
        assert "id" in project
        assert "created_at" in project

    async def test_create_project_duplicate_name(self, api_client: AsyncClient, test_project):
        """Test creating project with duplicate name."""
        response = await api_client.post("/projects", json={
            "name": "test-project",  # Will conflict with fixture
            "spec_content": "# Duplicate"
        })

        assert response.status_code == status.HTTP_409_CONFLICT
        error = response.json()
        assert "already exists" in error["detail"].lower()

    async def test_create_project_invalid_name(self, api_client: AsyncClient):
        """Test project creation with invalid name."""
        invalid_names = [
            "",  # Empty
            " ",  # Whitespace only
            "a" * 256,  # Too long
            "project/with/slashes",  # Invalid characters
            "../../../etc/passwd",  # Path traversal attempt
        ]

        for name in invalid_names:
            response = await api_client.post("/projects", json={
                "name": name,
                "spec_content": "# Test"
            })
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_create_project_invalid_spec(self, api_client: AsyncClient):
        """Test project creation with invalid specification."""
        response = await api_client.post("/projects", json={
            "name": "test-invalid-spec",
            "spec_content": "Too short"  # Should require minimum content
        })

        # Could be 422 or 400 depending on validation implementation
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_400_BAD_REQUEST
        ]

    async def test_list_projects(self, api_client: AsyncClient, test_project):
        """Test listing all projects."""
        response = await api_client.get("/projects")

        assert response.status_code == status.HTTP_200_OK
        projects = response.json()
        assert isinstance(projects, list)
        assert len(projects) >= 1  # At least test_project exists

        # Verify project structure
        for project in projects:
            assert "id" in project
            assert "name" in project
            assert "created_at" in project
            assert "status" in project

    async def test_get_project_by_id(self, api_client: AsyncClient, test_project):
        """Test getting specific project by ID."""
        response = await api_client.get(f"/projects/{test_project}")

        assert response.status_code == status.HTTP_200_OK
        project = response.json()
        assert project["id"] == str(test_project)
        assert "name" in project
        assert "spec_content" in project

    async def test_get_nonexistent_project(self, api_client: AsyncClient):
        """Test getting project that doesn't exist."""
        fake_id = uuid4()
        response = await api_client.get(f"/projects/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        error = response.json()
        assert "not found" in error["detail"].lower()

    async def test_delete_project(self, api_client: AsyncClient, test_project):
        """Test deleting a project."""
        response = await api_client.delete(f"/projects/{test_project}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify project is deleted
        get_response = await api_client.get(f"/projects/{test_project}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_project(self, api_client: AsyncClient, test_project):
        """Test updating project details."""
        update_data = {
            "name": "updated-project-name",
            "description": "Updated description"
        }

        response = await api_client.patch(f"/projects/{test_project}", json=update_data)

        # Depending on implementation
        if response.status_code == status.HTTP_501_NOT_IMPLEMENTED:
            pytest.skip("Project update not implemented")

        assert response.status_code == status.HTTP_200_OK
        project = response.json()
        assert project["name"] == update_data["name"]


@pytest.mark.api
@pytest.mark.asyncio
class TestSessionEndpoints:
    """Test session-related API endpoints."""

    async def test_create_session(self, api_client: AsyncClient, test_project):
        """Test creating a new session."""
        session_data = {
            "project_id": str(test_project),
            "session_type": "coding",
            "model": "claude-sonnet-3-5"
        }

        response = await api_client.post("/sessions", json=session_data)

        assert response.status_code == status.HTTP_201_CREATED
        session = response.json()
        assert session["project_id"] == str(test_project)
        assert session["status"] == "pending"
        assert "id" in session

    async def test_start_session(self, api_client: AsyncClient, test_session):
        """Test starting a session."""
        response = await api_client.post(f"/sessions/{test_session}/start")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["status"] in ["in_progress", "running"]

    async def test_stop_session(self, api_client: AsyncClient, test_session):
        """Test stopping a session."""
        response = await api_client.post(f"/sessions/{test_session}/stop")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["status"] in ["stopped", "completed", "cancelled"]

    async def test_get_session_status(self, api_client: AsyncClient, test_session):
        """Test getting session status."""
        response = await api_client.get(f"/sessions/{test_session}/status")

        assert response.status_code == status.HTTP_200_OK
        status_data = response.json()
        assert "status" in status_data
        assert "started_at" in status_data
        assert "model" in status_data

    async def test_list_project_sessions(self, api_client: AsyncClient, test_project, test_session):
        """Test listing sessions for a project."""
        response = await api_client.get(f"/projects/{test_project}/sessions")

        assert response.status_code == status.HTTP_200_OK
        sessions = response.json()
        assert isinstance(sessions, list)
        assert len(sessions) >= 1
        assert any(s["id"] == str(test_session) for s in sessions)

    async def test_get_session_logs(self, api_client: AsyncClient, test_session):
        """Test retrieving session logs."""
        response = await api_client.get(f"/sessions/{test_session}/logs")

        assert response.status_code == status.HTTP_200_OK
        logs = response.json()
        assert isinstance(logs, (list, dict))  # Could be list of entries or structured log


@pytest.mark.api
@pytest.mark.asyncio
class TestTaskEndpoints:
    """Test task-related API endpoints."""

    async def test_list_project_tasks(self, api_client: AsyncClient, test_project, test_task):
        """Test listing tasks for a project."""
        response = await api_client.get(f"/projects/{test_project}/tasks")

        assert response.status_code == status.HTTP_200_OK
        tasks = response.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1

    async def test_get_task_details(self, api_client: AsyncClient, test_task):
        """Test getting task details."""
        response = await api_client.get(f"/tasks/{test_task}")

        assert response.status_code == status.HTTP_200_OK
        task = response.json()
        assert task["id"] == test_task
        assert "name" in task
        assert "description" in task
        assert "status" in task

    async def test_update_task_status(self, api_client: AsyncClient, test_task):
        """Test updating task status."""
        update_data = {
            "status": "in_progress"
        }

        response = await api_client.patch(f"/tasks/{test_task}/status", json=update_data)

        assert response.status_code == status.HTTP_200_OK
        task = response.json()
        assert task["status"] == "in_progress"

    async def test_get_next_task(self, api_client: AsyncClient, test_project):
        """Test getting the next task to work on."""
        response = await api_client.get(f"/projects/{test_project}/next-task")

        # Could return 200 with task or 204 if no tasks available
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]

        if response.status_code == status.HTTP_200_OK:
            task = response.json()
            assert "id" in task
            assert "name" in task
            assert task["status"] == "pending"


@pytest.mark.api
@pytest.mark.asyncio
class TestProgressEndpoints:
    """Test progress tracking endpoints."""

    async def test_get_project_progress(self, api_client: AsyncClient, test_project):
        """Test getting project progress."""
        response = await api_client.get(f"/projects/{test_project}/progress")

        assert response.status_code == status.HTTP_200_OK
        progress = response.json()
        assert "total_epics" in progress
        assert "completed_epics" in progress
        assert "total_tasks" in progress
        assert "completed_tasks" in progress
        assert "percentage" in progress
        assert 0 <= progress["percentage"] <= 100

    async def test_get_epic_progress(self, api_client: AsyncClient, test_epic):
        """Test getting epic progress."""
        response = await api_client.get(f"/epics/{test_epic}/progress")

        assert response.status_code == status.HTTP_200_OK
        progress = response.json()
        assert "total_tasks" in progress
        assert "completed_tasks" in progress


@pytest.mark.api
@pytest.mark.asyncio
class TestQualityEndpoints:
    """Test quality and review endpoints."""

    async def test_get_project_quality(self, api_client: AsyncClient, test_project):
        """Test getting project quality metrics."""
        response = await api_client.get(f"/projects/{test_project}/quality")

        assert response.status_code == status.HTTP_200_OK
        quality = response.json()
        assert "overall_score" in quality
        assert "metrics" in quality
        assert isinstance(quality["metrics"], dict)

    async def test_trigger_review(self, api_client: AsyncClient, test_session):
        """Test triggering a quality review."""
        response = await api_client.post(f"/sessions/{test_session}/review")

        assert response.status_code in [
            status.HTTP_202_ACCEPTED,  # Review started
            status.HTTP_200_OK  # Review completed immediately
        ]

        if response.status_code == status.HTTP_200_OK:
            review = response.json()
            assert "score" in review
            assert "recommendations" in review

    async def test_get_review_history(self, api_client: AsyncClient, test_project):
        """Test getting review history."""
        response = await api_client.get(f"/projects/{test_project}/reviews")

        assert response.status_code == status.HTTP_200_OK
        reviews = response.json()
        assert isinstance(reviews, list)


@pytest.mark.api
@pytest.mark.asyncio
class TestHealthEndpoints:
    """Test health and status endpoints."""

    async def test_health_check(self, api_client: AsyncClient):
        """Test health check endpoint."""
        response = await api_client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        health = response.json()
        assert health["status"] == "healthy"
        assert "database" in health
        assert "version" in health

    async def test_readiness_check(self, api_client: AsyncClient):
        """Test readiness check endpoint."""
        response = await api_client.get("/ready")

        assert response.status_code == status.HTTP_200_OK
        ready = response.json()
        assert ready["ready"] is True

    async def test_api_version(self, api_client: AsyncClient):
        """Test API version endpoint."""
        response = await api_client.get("/version")

        assert response.status_code == status.HTTP_200_OK
        version = response.json()
        assert "api_version" in version
        assert "yokeflow_version" in version


@pytest.mark.api
@pytest.mark.asyncio
class TestAuthenticationEndpoints:
    """Test authentication and authorization."""

    async def test_login(self, api_client: AsyncClient):
        """Test login endpoint."""
        login_data = {
            "username": "test_user",
            "password": "test_password"
        }

        response = await api_client.post("/auth/login", json=login_data)

        # Might be 501 if not implemented
        if response.status_code == status.HTTP_501_NOT_IMPLEMENTED:
            pytest.skip("Authentication not implemented")

        assert response.status_code == status.HTTP_200_OK
        auth = response.json()
        assert "access_token" in auth
        assert "token_type" in auth

    async def test_unauthorized_access(self):
        """Test accessing protected endpoint without auth."""
        # Create client without auth header
        from api.main import app
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/projects")

            # Might allow access in dev mode
            if response.status_code == status.HTTP_200_OK:
                pytest.skip("Authentication disabled in development")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.asyncio
class TestWebSocketEndpoints:
    """Test WebSocket connections."""

    async def test_websocket_connection(self, api_client: AsyncClient, test_project):
        """Test WebSocket connection establishment."""
        # WebSocket testing requires special client
        pytest.skip("WebSocket testing requires specialized setup")

    async def test_websocket_progress_updates(self, mock_websocket):
        """Test WebSocket progress updates."""
        # Mock implementation
        await mock_websocket.send_json({"type": "subscribe", "project_id": "test"})
        response = await mock_websocket.receive_json()
        assert response["type"] == "ping"


@pytest.mark.api
@pytest.mark.asyncio
class TestErrorHandling:
    """Test API error handling."""

    async def test_invalid_json(self, api_client: AsyncClient):
        """Test sending invalid JSON."""
        response = await api_client.post(
            "/projects",
            content="not json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_missing_required_fields(self, api_client: AsyncClient):
        """Test missing required fields."""
        response = await api_client.post("/projects", json={})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        error = response.json()
        assert "detail" in error

    async def test_method_not_allowed(self, api_client: AsyncClient):
        """Test using wrong HTTP method."""
        response = await api_client.put("/projects")  # Should be POST

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    async def test_rate_limiting(self, api_client: AsyncClient):
        """Test rate limiting (if implemented)."""
        # Send many requests quickly
        responses = []
        for _ in range(100):
            response = await api_client.get("/projects")
            responses.append(response.status_code)

        # Check if rate limiting kicked in
        if status.HTTP_429_TOO_MANY_REQUESTS in responses:
            assert True  # Rate limiting works
        else:
            pytest.skip("Rate limiting not implemented")