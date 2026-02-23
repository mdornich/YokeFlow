"""
YokeFlow Error Hierarchy

Provides a structured error framework for consistent error handling across the platform.
All custom exceptions include error categories, recoverability flags, and error codes.
"""

from enum import Enum
from typing import Optional, Dict, Any


class ErrorCategory(str, Enum):
    """Categories of errors for grouping and monitoring"""
    DATABASE = "database"
    NETWORK = "network"
    SANDBOX = "sandbox"
    VALIDATION = "validation"
    TOOL_EXECUTION = "tool_execution"
    SESSION = "session"
    RESOURCE = "resource"
    CONFIGURATION = "configuration"
    CLAUDE_API = "claude_api"
    INTERVENTION = "intervention"


class YokeFlowError(Exception):
    """
    Base exception for all YokeFlow errors.

    Attributes:
        category: Error category for grouping
        recoverable: Whether the error can be recovered from
        error_code: Unique error code for tracking
        context: Additional context about the error
    """
    category: ErrorCategory = ErrorCategory.VALIDATION
    error_code: str = "UNKNOWN"

    def __init__(
        self,
        message: str,
        recoverable: bool = False,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.recoverable = recoverable
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/API responses"""
        return {
            "error_code": self.error_code,
            "category": self.category.value,
            "message": str(self),
            "recoverable": self.recoverable,
            "context": self.context
        }


# ============================================================================
# Database Errors
# ============================================================================

class DatabaseError(YokeFlowError):
    """Base class for database-related errors"""
    category = ErrorCategory.DATABASE
    error_code = "DB_ERROR"


class DatabaseConnectionError(DatabaseError):
    """Database connection failed"""
    error_code = "DB_CONNECTION"

    def __init__(self, message: str, retry_count: int = 0, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        self.context["retry_count"] = retry_count


class DatabaseQueryError(DatabaseError):
    """Database query execution failed"""
    error_code = "DB_QUERY"

    def __init__(self, message: str, query: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        if query:
            self.context["query"] = query


class DatabaseTransactionError(DatabaseError):
    """Database transaction failed"""
    error_code = "DB_TRANSACTION"

    def __init__(self, message: str, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)


class DatabasePoolExhaustedError(DatabaseError):
    """Database connection pool exhausted"""
    error_code = "DB_POOL_EXHAUSTED"

    def __init__(self, message: str = "Connection pool exhausted", **kwargs):
        super().__init__(message, recoverable=True, **kwargs)


# ============================================================================
# Network Errors
# ============================================================================

class NetworkError(YokeFlowError):
    """Base class for network-related errors"""
    category = ErrorCategory.NETWORK
    error_code = "NET_ERROR"


class ClaudeAPIError(NetworkError):
    """Claude API request failed"""
    category = ErrorCategory.CLAUDE_API
    error_code = "CLAUDE_API"

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, recoverable=True, **kwargs)
        if status_code:
            self.context["status_code"] = status_code


class ClaudeRateLimitError(ClaudeAPIError):
    """Claude API rate limit exceeded"""
    error_code = "CLAUDE_RATE_LIMIT"

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        if retry_after:
            self.context["retry_after"] = retry_after


class ClaudeAuthenticationError(ClaudeAPIError):
    """Claude API authentication failed"""
    error_code = "CLAUDE_AUTH"

    def __init__(self, message: str = "Invalid API key", **kwargs):
        # Don't pass recoverable to super since ClaudeAPIError already sets it
        kwargs.pop('recoverable', None)
        super().__init__(message, **kwargs)
        self.recoverable = False


# ============================================================================
# Sandbox Errors
# ============================================================================

class SandboxError(YokeFlowError):
    """Base class for sandbox-related errors"""
    category = ErrorCategory.SANDBOX
    error_code = "SANDBOX_ERROR"


class SandboxStartError(SandboxError):
    """Failed to start sandbox container"""
    error_code = "SANDBOX_START"

    def __init__(self, message: str, container_id: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        if container_id:
            self.context["container_id"] = container_id


class SandboxStopError(SandboxError):
    """Failed to stop sandbox container"""
    error_code = "SANDBOX_STOP"

    def __init__(self, message: str, container_id: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        if container_id:
            self.context["container_id"] = container_id


class SandboxCommandError(SandboxError):
    """Command execution failed in sandbox"""
    error_code = "SANDBOX_COMMAND"

    def __init__(
        self,
        message: str,
        command: Optional[str] = None,
        exit_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, recoverable=False, **kwargs)
        if command:
            self.context["command"] = command
        if exit_code is not None:
            self.context["exit_code"] = exit_code


# ============================================================================
# Validation Errors
# ============================================================================

class ValidationError(YokeFlowError):
    """Base class for validation errors"""
    category = ErrorCategory.VALIDATION
    error_code = "VALIDATION_ERROR"

    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        if field:
            self.context["field"] = field


class ProjectValidationError(ValidationError):
    """Project configuration validation failed"""
    error_code = "PROJECT_VALIDATION"


class SpecValidationError(ValidationError):
    """App specification validation failed"""
    error_code = "SPEC_VALIDATION"


class TaskValidationError(ValidationError):
    """Task validation failed"""
    error_code = "TASK_VALIDATION"

    def __init__(self, message: str, task_id: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        if task_id:
            self.context["task_id"] = task_id


# ============================================================================
# Tool Execution Errors
# ============================================================================

class ToolExecutionError(YokeFlowError):
    """Base class for tool execution errors"""
    category = ErrorCategory.TOOL_EXECUTION
    error_code = "TOOL_ERROR"

    def __init__(
        self,
        tool_name: str,
        message: str,
        recoverable: bool = True,
        **kwargs
    ):
        super().__init__(f"{tool_name}: {message}", recoverable, **kwargs)
        self.tool_name = tool_name
        self.context["tool_name"] = tool_name


class SecurityBlockedError(ToolExecutionError):
    """Command blocked by security policy"""
    error_code = "SECURITY_BLOCKED"

    def __init__(self, tool_name: str, command: str, **kwargs):
        super().__init__(
            tool_name,
            f"Command blocked by security policy: {command}",
            recoverable=False,
            **kwargs
        )
        self.context["blocked_command"] = command


# ============================================================================
# Session Errors
# ============================================================================

class SessionError(YokeFlowError):
    """Base class for session-related errors"""
    category = ErrorCategory.SESSION
    error_code = "SESSION_ERROR"


class SessionNotFoundError(SessionError):
    """Session not found in database"""
    error_code = "SESSION_NOT_FOUND"

    def __init__(self, session_id: str, **kwargs):
        super().__init__(f"Session not found: {session_id}", **kwargs)
        self.context["session_id"] = session_id


class SessionAlreadyRunningError(SessionError):
    """Session is already running"""
    error_code = "SESSION_RUNNING"

    def __init__(self, session_id: str, **kwargs):
        super().__init__(f"Session already running: {session_id}", **kwargs)
        self.context["session_id"] = session_id


class CheckpointNotFoundError(SessionError):
    """Session checkpoint not found"""
    error_code = "CHECKPOINT_NOT_FOUND"

    def __init__(self, checkpoint_id: str, **kwargs):
        super().__init__(f"Checkpoint not found: {checkpoint_id}", **kwargs)
        self.context["checkpoint_id"] = checkpoint_id


class CheckpointInvalidError(SessionError):
    """Session checkpoint is invalid or corrupted"""
    error_code = "CHECKPOINT_INVALID"

    def __init__(self, checkpoint_id: str, reason: str, **kwargs):
        super().__init__(f"Invalid checkpoint {checkpoint_id}: {reason}", **kwargs)
        self.context["checkpoint_id"] = checkpoint_id
        self.context["reason"] = reason


# ============================================================================
# Intervention Errors
# ============================================================================

class InterventionError(YokeFlowError):
    """Base class for intervention system errors"""
    category = ErrorCategory.INTERVENTION
    error_code = "INTERVENTION_ERROR"


class PausedSessionNotFoundError(InterventionError):
    """Paused session not found"""
    error_code = "PAUSED_SESSION_NOT_FOUND"

    def __init__(self, session_id: str, **kwargs):
        super().__init__(f"Paused session not found: {session_id}", **kwargs)
        self.context["session_id"] = session_id


class SessionAlreadyResolvedError(InterventionError):
    """Session has already been resolved"""
    error_code = "SESSION_ALREADY_RESOLVED"

    def __init__(self, session_id: str, **kwargs):
        super().__init__(f"Session already resolved: {session_id}", **kwargs)
        self.context["session_id"] = session_id


# ============================================================================
# Resource Errors
# ============================================================================

class ResourceError(YokeFlowError):
    """Base class for resource management errors"""
    category = ErrorCategory.RESOURCE
    error_code = "RESOURCE_ERROR"


class ResourceExhaustedError(ResourceError):
    """System resources exhausted"""
    error_code = "RESOURCE_EXHAUSTED"

    def __init__(self, resource_type: str, **kwargs):
        super().__init__(
            f"Resource exhausted: {resource_type}",
            recoverable=True,
            **kwargs
        )
        self.context["resource_type"] = resource_type


class PortAllocationError(ResourceError):
    """Failed to allocate port for session"""
    error_code = "PORT_ALLOCATION"

    def __init__(self, message: str = "No available ports", **kwargs):
        super().__init__(message, recoverable=True, **kwargs)


# ============================================================================
# Configuration Errors
# ============================================================================

class ConfigurationError(YokeFlowError):
    """Base class for configuration errors"""
    category = ErrorCategory.CONFIGURATION
    error_code = "CONFIG_ERROR"

    def __init__(self, message: str, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)


class MissingConfigError(ConfigurationError):
    """Required configuration missing"""
    error_code = "CONFIG_MISSING"

    def __init__(self, config_key: str, **kwargs):
        super().__init__(f"Missing required config: {config_key}", **kwargs)
        self.context["config_key"] = config_key


class InvalidConfigError(ConfigurationError):
    """Configuration value is invalid"""
    error_code = "CONFIG_INVALID"

    def __init__(self, config_key: str, value: Any, reason: str, **kwargs):
        super().__init__(
            f"Invalid config '{config_key}' = {value}: {reason}",
            **kwargs
        )
        self.context["config_key"] = config_key
        self.context["value"] = str(value)
        self.context["reason"] = reason
