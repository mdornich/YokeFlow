"""
Tests for structured logging module.

Tests JSON formatting, context variables, performance logging, and development formatting.
"""

import json
import logging
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from core.structured_logging import (
    StructuredLogFormatter,
    DevelopmentFormatter,
    PerformanceLogger,
    setup_structured_logging,
    set_correlation_id,
    set_session_id,
    set_project_id,
    get_correlation_id,
    get_session_id,
    get_project_id,
    clear_context,
    get_logger
)


class TestStructuredLogFormatter:
    """Test JSON log formatter"""

    def test_basic_log_formatting(self):
        """Test basic log message formatting"""
        formatter = StructuredLogFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_func"
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test message"
        assert log_data["location"]["file"] == "test.py"
        assert log_data["location"]["line"] == 42
        assert log_data["location"]["function"] == "test_func"
        assert "timestamp" in log_data

    def test_log_with_context_variables(self):
        """Test logging with context variables set"""
        formatter = StructuredLogFormatter()

        # Set context
        set_correlation_id("corr-123")
        set_session_id("sess-456")
        set_project_id("proj-789")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Message",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["correlation_id"] == "corr-123"
        assert log_data["session_id"] == "sess-456"
        assert log_data["project_id"] == "proj-789"

        # Cleanup
        clear_context()

    def test_log_with_extra_fields(self):
        """Test logging with extra fields"""
        formatter = StructuredLogFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Message",
            args=(),
            exc_info=None
        )

        # Add extra fields
        record.user_id = "user-123"
        record.task_id = 42
        record.custom_data = {"key": "value"}

        output = formatter.format(record)
        log_data = json.loads(output)

        assert "extra" in log_data
        assert log_data["extra"]["user_id"] == "user-123"
        assert log_data["extra"]["task_id"] == 42
        assert log_data["extra"]["custom_data"] == {"key": "value"}

    def test_log_with_exception(self):
        """Test logging with exception information"""
        formatter = StructuredLogFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        assert "exception" in log_data
        assert log_data["exception"]["type"] == "ValueError"
        assert log_data["exception"]["message"] == "Test error"
        assert "stacktrace" in log_data["exception"]

    def test_serialize_value_types(self):
        """Test serialization of different value types"""
        formatter = StructuredLogFormatter()

        # UUID
        uuid_val = uuid4()
        assert formatter.serialize_value(uuid_val) == str(uuid_val)

        # Path
        path_val = Path("/test/path")
        assert formatter.serialize_value(path_val) == str(path_val)

        # Dict with nested values
        dict_val = {"uuid": uuid_val, "path": path_val, "num": 42}
        result = formatter.serialize_value(dict_val)
        assert result["uuid"] == str(uuid_val)
        assert result["path"] == str(path_val)
        assert result["num"] == 42

        # List
        list_val = [1, "test", uuid_val]
        result = formatter.serialize_value(list_val)
        assert result == [1, "test", str(uuid_val)]


class TestDevelopmentFormatter:
    """Test development-friendly formatter"""

    def test_basic_formatting(self):
        """Test basic development log formatting"""
        formatter = DevelopmentFormatter(use_colors=False)
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_func"
        )

        output = formatter.format(record)

        assert "INFO" in output
        assert "test.logger:42" in output
        assert "Test message" in output

    def test_formatting_with_context(self):
        """Test development formatting with context"""
        formatter = DevelopmentFormatter(use_colors=False)

        set_session_id("session-12345678-abcd")
        set_project_id("project-87654321-dcba")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Message",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)

        # Should show truncated IDs (first 8 chars)
        assert "session_id=session-" in output
        assert "project_id=project-" in output

        clear_context()


class TestContextVariables:
    """Test context variable management"""

    def test_set_and_get_correlation_id(self):
        """Test correlation ID context"""
        test_id = "test-correlation-id"
        set_correlation_id(test_id)
        assert get_correlation_id() == test_id
        clear_context()
        assert get_correlation_id() is None

    def test_set_and_get_session_id(self):
        """Test session ID context"""
        test_id = "test-session-id"
        set_session_id(test_id)
        assert get_session_id() == test_id
        clear_context()
        assert get_session_id() is None

    def test_set_and_get_project_id(self):
        """Test project ID context"""
        test_id = "test-project-id"
        set_project_id(test_id)
        assert get_project_id() == test_id
        clear_context()
        assert get_project_id() is None

    def test_clear_all_context(self):
        """Test clearing all context variables"""
        set_correlation_id("corr")
        set_session_id("sess")
        set_project_id("proj")

        clear_context()

        assert get_correlation_id() is None
        assert get_session_id() is None
        assert get_project_id() is None


class TestPerformanceLogger:
    """Test performance measurement logger"""

    def test_performance_logging_success(self, caplog):
        """Test performance logging for successful operation"""
        caplog.set_level(logging.DEBUG)

        with PerformanceLogger("test_operation", {"query_type": "select"}):
            pass  # Simulate operation

        # Should have logged completion
        assert any("test_operation" in record.message for record in caplog.records)
        assert any("completed" in record.message for record in caplog.records)

    def test_performance_logging_slow_operation(self, caplog):
        """Test warning for slow operations"""
        import time
        caplog.set_level(logging.WARNING)

        with PerformanceLogger("slow_operation"):
            time.sleep(1.1)  # > 1 second threshold

        # Should have logged warning
        assert any(
            "slow_operation" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )

    def test_performance_logging_error(self, caplog):
        """Test performance logging when error occurs"""
        caplog.set_level(logging.ERROR)

        with pytest.raises(ValueError):
            with PerformanceLogger("error_operation"):
                raise ValueError("Test error")

        # Should have logged error
        assert any(
            "error_operation" in record.message and "failed" in record.message
            for record in caplog.records
        )


class TestSetupStructuredLogging:
    """Test logging setup"""

    def test_setup_json_logging(self, tmp_path):
        """Test setup with JSON formatting"""
        log_file = tmp_path / "test.log"
        logger = setup_structured_logging(
            level="INFO",
            format_type="json",
            log_file=log_file
        )

        # Log a message
        logger.info("Test message")

        # Verify file was created and contains JSON
        assert log_file.exists()
        with open(log_file) as f:
            log_line = f.readline()
            log_data = json.loads(log_line)
            assert log_data["message"] == "Test message"

    def test_setup_dev_logging(self):
        """Test setup with development formatting"""
        logger = setup_structured_logging(
            level="DEBUG",
            format_type="dev"
        )

        assert logger.level == logging.DEBUG
        assert len(logger.handlers) > 0

    def test_setup_with_custom_level(self):
        """Test setup with custom log level"""
        logger = setup_structured_logging(level="WARNING")
        assert logger.level == logging.WARNING


class TestGetLogger:
    """Test logger retrieval"""

    def test_get_logger_returns_logger(self):
        """Test getting a named logger"""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_logger_with_extra_fields(self, caplog):
        """Test logging with extra fields"""
        caplog.set_level(logging.INFO)
        logger = get_logger("test")

        logger.info("Test message", extra={"custom_field": "custom_value"})

        # Verify extra field is present
        assert any(
            hasattr(record, 'custom_field') and record.custom_field == "custom_value"
            for record in caplog.records
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
