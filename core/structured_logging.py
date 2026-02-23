"""
Structured Logging for YokeFlow

Provides JSON-formatted logging for production deployments with support for
ELK, Datadog, CloudWatch, and other log aggregation systems.

Features:
- JSON-formatted logs with consistent schema
- Correlation IDs for request tracking
- Session/project context injection
- Performance-optimized formatting
- Development-friendly plain text mode
"""

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID


# Context variables for tracking request/session context
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
_session_id: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_project_id: ContextVar[Optional[str]] = ContextVar('project_id', default=None)
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class StructuredLogFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format with consistent schema:
    {
        "timestamp": "2026-01-05T10:30:45.123Z",
        "level": "INFO",
        "logger": "core.agent",
        "message": "Session started",
        "correlation_id": "abc-123",
        "session_id": "uuid",
        "project_id": "uuid",
        "extra": {...}
    }
    """

    RESERVED_ATTRS = {
        'name', 'msg', 'args', 'created', 'filename', 'funcName', 'levelname',
        'levelno', 'lineno', 'module', 'msecs', 'message', 'pathname', 'process',
        'processName', 'relativeCreated', 'thread', 'threadName', 'exc_info',
        'exc_text', 'stack_info'
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data: Dict[str, Any] = {
            "timestamp": self.format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName
        }

        # Add context from context variables
        correlation_id = _correlation_id.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        session_id = _session_id.get()
        if session_id:
            log_data["session_id"] = session_id

        project_id = _project_id.get()
        if project_id:
            log_data["project_id"] = project_id

        request_id = _request_id.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add custom fields from extra= parameter
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith('_'):
                extra_fields[key] = self.serialize_value(value)

        if extra_fields:
            log_data["extra"] = extra_fields

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": self.formatException(record.exc_info)
            }

        # Add stack trace if present
        if record.stack_info:
            log_data["stack_trace"] = record.stack_info

        return json.dumps(log_data, default=str)

    @staticmethod
    def format_timestamp(created: float) -> str:
        """Format timestamp as ISO 8601 with milliseconds"""
        dt = datetime.utcfromtimestamp(created)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    @staticmethod
    def serialize_value(value: Any) -> Any:
        """Serialize value for JSON output"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, (UUID, Path)):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: StructuredLogFormatter.serialize_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [StructuredLogFormatter.serialize_value(v) for v in value]
        else:
            return str(value)


class DevelopmentFormatter(logging.Formatter):
    """
    Human-friendly formatter for development.

    Example output:
    2026-01-05 10:30:45.123 | INFO     | core.agent:42 | Session started [session_id=abc-123]
    """

    # Color codes for terminal output
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for human reading"""
        # Timestamp
        timestamp = datetime.utcfromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Level with color
        level = record.levelname.ljust(8)
        if self.use_colors:
            color = self.COLORS.get(record.levelname, '')
            reset = self.COLORS['RESET']
            level = f"{color}{level}{reset}"

        # Location
        location = f"{record.name}:{record.lineno}"

        # Message
        message = record.getMessage()

        # Build context suffix
        context_parts = []

        correlation_id = _correlation_id.get()
        if correlation_id:
            context_parts.append(f"correlation_id={correlation_id}")

        session_id = _session_id.get()
        if session_id:
            context_parts.append(f"session_id={session_id[:8]}")

        project_id = _project_id.get()
        if project_id:
            context_parts.append(f"project_id={project_id[:8]}")

        # Add custom fields
        for key, value in record.__dict__.items():
            if key not in StructuredLogFormatter.RESERVED_ATTRS and not key.startswith('_'):
                context_parts.append(f"{key}={value}")

        context = f" [{', '.join(context_parts)}]" if context_parts else ""

        # Build final message
        log_line = f"{timestamp} | {level} | {location} | {message}{context}"

        # Add exception if present
        if record.exc_info:
            log_line += "\n" + self.formatException(record.exc_info)

        return log_line


class PerformanceLogger:
    """
    Performance measurement logger with structured output.

    Usage:
        with PerformanceLogger("database_query", {"query_type": "select"}):
            result = await db.fetch(...)
    """

    def __init__(self, operation: str, context: Optional[Dict[str, Any]] = None):
        self.operation = operation
        self.context = context or {}
        self.start_time = 0.0
        self.logger = logging.getLogger(f"performance.{operation}")

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000

        log_extra = {
            "operation": self.operation,
            "duration_ms": round(duration_ms, 2),
            **self.context
        }

        if exc_type:
            log_extra["error"] = str(exc_val)
            self.logger.error(
                f"{self.operation} failed after {duration_ms:.2f}ms",
                extra=log_extra
            )
        elif duration_ms > 1000:  # Warn if > 1 second
            self.logger.warning(
                f"{self.operation} took {duration_ms:.2f}ms",
                extra=log_extra
            )
        else:
            self.logger.debug(
                f"{self.operation} completed in {duration_ms:.2f}ms",
                extra=log_extra
            )


def setup_structured_logging(
    level: str = "INFO",
    format_type: str = "json",
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Configure structured logging for YokeFlow.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: "json" for production, "dev" for development
        log_file: Optional file path for logging output

    Returns:
        Configured root logger
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatter
    if format_type == "json":
        formatter = StructuredLogFormatter()
    else:
        formatter = DevelopmentFormatter(use_colors=True)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        # Always use JSON for file output
        file_handler.setFormatter(StructuredLogFormatter())
        root_logger.addHandler(file_handler)

    return root_logger


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context"""
    _correlation_id.set(correlation_id)


def set_session_id(session_id: str) -> None:
    """Set session ID for current context"""
    _session_id.set(session_id)


def set_project_id(project_id: str) -> None:
    """Set project ID for current context"""
    _project_id.set(project_id)


def set_request_id(request_id: str) -> None:
    """Set request ID for current context"""
    _request_id.set(request_id)


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID"""
    return _correlation_id.get()


def get_session_id() -> Optional[str]:
    """Get current session ID"""
    return _session_id.get()


def get_project_id() -> Optional[str]:
    """Get current project ID"""
    return _project_id.get()


def get_request_id() -> Optional[str]:
    """Get current request ID"""
    return _request_id.get()


def clear_context() -> None:
    """Clear all context variables"""
    _correlation_id.set(None)
    _session_id.set(None)
    _project_id.set(None)
    _request_id.set(None)


# Convenience function for getting a logger with module name
def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    Usage:
        logger = get_logger(__name__)
        logger.info("Message", extra={"key": "value"})
    """
    return logging.getLogger(name)
