"""
Tests for Database Retry Logic
===============================

Comprehensive test suite for database retry functionality including:
- Exponential backoff calculation
- Transient error detection
- Retry decorator behavior
- Connection pool retry integration
- Statistics tracking
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import asyncpg

from core.database_retry import (
    with_retry,
    RetryConfig,
    is_transient_error,
    calculate_delay,
    get_retry_stats,
    reset_retry_stats,
)


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.jitter_range == 0.1

    def test_custom_config(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=60.0,
            exponential_base=3.0,
            jitter=False,
        )
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 3.0
        assert config.jitter is False


class TestTransientErrorDetection:
    """Test transient error detection logic."""

    def test_connection_errors_are_transient(self):
        """Test that connection errors are detected as transient."""
        errors = [
            asyncpg.ConnectionDoesNotExistError("connection does not exist"),
            asyncpg.ConnectionFailureError("connection failed"),
            asyncpg.InterfaceError("interface error"),
        ]

        for error in errors:
            assert is_transient_error(error), f"{type(error).__name__} should be transient"

    def test_postgres_error_with_transient_sqlstate(self):
        """Test PostgresError with transient SQL state."""
        # Create mock PostgresError with sqlstate attribute
        error = asyncpg.PostgresError()
        error.sqlstate = '08006'  # connection_failure

        assert is_transient_error(error)

    def test_postgres_error_with_deadlock(self):
        """Test deadlock detection."""
        error = asyncpg.PostgresError()
        error.sqlstate = '40P01'  # deadlock_detected

        assert is_transient_error(error)

    def test_message_based_detection(self):
        """Test error detection based on message content."""
        transient_messages = [
            "connection refused",
            "connection reset by peer",
            "connection timeout",
            "too many connections",
            "deadlock detected",
            "temporary failure in name resolution",
        ]

        for msg in transient_messages:
            error = Exception(msg)
            assert is_transient_error(error), f"Error with message '{msg}' should be transient"

    def test_non_transient_errors(self):
        """Test that non-transient errors are not detected as transient."""
        errors = [
            ValueError("invalid input"),
            KeyError("missing key"),
            TypeError("wrong type"),
            Exception("some other error"),
        ]

        for error in errors:
            assert not is_transient_error(error), f"{type(error).__name__} should not be transient"


class TestDelayCalculation:
    """Test retry delay calculation."""

    def test_exponential_backoff(self):
        """Test exponential backoff without jitter."""
        config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=30.0,
            jitter=False
        )

        # Attempt 0: 1.0 * 2^0 = 1.0
        assert calculate_delay(0, config) == 1.0

        # Attempt 1: 1.0 * 2^1 = 2.0
        assert calculate_delay(1, config) == 2.0

        # Attempt 2: 1.0 * 2^2 = 4.0
        assert calculate_delay(2, config) == 4.0

        # Attempt 3: 1.0 * 2^3 = 8.0
        assert calculate_delay(3, config) == 8.0

    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        config = RetryConfig(
            base_delay=10.0,
            exponential_base=2.0,
            max_delay=20.0,
            jitter=False
        )

        # Attempt 2: 10.0 * 2^2 = 40.0, capped at 20.0
        assert calculate_delay(2, config) == 20.0

        # Attempt 10: would be huge, capped at 20.0
        assert calculate_delay(10, config) == 20.0

    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delay."""
        config = RetryConfig(
            base_delay=10.0,
            exponential_base=2.0,
            jitter=True,
            jitter_range=0.1  # ±10%
        )

        # Run multiple times to check variance
        delays = [calculate_delay(0, config) for _ in range(100)]

        # Base delay is 10.0, jitter range is ±1.0 (10%)
        # All delays should be in range [9.0, 11.0]
        assert all(9.0 <= d <= 11.0 for d in delays)

        # Should have variance (not all the same)
        assert len(set(delays)) > 1

    def test_delay_always_non_negative(self):
        """Test that delay is never negative even with jitter."""
        config = RetryConfig(
            base_delay=0.1,
            jitter=True,
            jitter_range=1.0  # Large jitter
        )

        # Run multiple times
        delays = [calculate_delay(0, config) for _ in range(100)]

        # All delays should be non-negative
        assert all(d >= 0.0 for d in delays)


class TestRetryDecorator:
    """Test the @with_retry decorator."""

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self):
        """Test that successful operations don't retry."""
        call_count = 0

        @with_retry()
        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_operation()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_transient_error_retries(self):
        """Test that transient errors trigger retries."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def flaky_operation():
            nonlocal call_count
            call_count += 1

            if call_count < 3:
                raise asyncpg.ConnectionFailureError("connection failed")

            return "success"

        result = await flaky_operation()

        assert result == "success"
        assert call_count == 3  # Failed twice, succeeded on third try

    @pytest.mark.asyncio
    async def test_non_transient_error_fails_immediately(self):
        """Test that non-transient errors fail immediately without retry."""
        call_count = 0

        @with_retry()
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            await failing_operation()

        assert call_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Test that operation fails after max retries exhausted."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise asyncpg.ConnectionFailureError("connection failed")

        with pytest.raises(asyncpg.ConnectionFailureError):
            await always_fails()

        assert call_count == 4  # Initial attempt + 3 retries

    @pytest.mark.asyncio
    async def test_custom_retry_config(self):
        """Test decorator with custom retry configuration."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=5, base_delay=0.01))
        async def custom_retry():
            nonlocal call_count
            call_count += 1

            if call_count < 4:
                raise asyncpg.ConnectionFailureError("connection failed")

            return "success"

        result = await custom_retry()

        assert result == "success"
        assert call_count == 4


class TestDatabaseIntegration:
    """Test integration with database operations."""

    @pytest.mark.asyncio
    async def test_connection_pool_with_retry(self):
        """Test connection pool acquisition with retry."""
        # Create mock pool that fails first, then succeeds
        mock_pool = AsyncMock()
        attempt = 0

        async def acquire_with_failure():
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise asyncpg.ConnectionFailureError("connection failed")
            return MagicMock()

        mock_pool.acquire = AsyncMock(side_effect=acquire_with_failure)

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def acquire_connection():
            return await mock_pool.acquire()

        conn = await acquire_connection()

        assert conn is not None
        assert attempt == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_query_execution_with_retry(self):
        """Test query execution with retry logic."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def execute_query():
            nonlocal call_count
            call_count += 1

            if call_count < 2:
                # Simulate transient database error
                error = asyncpg.PostgresError()
                error.sqlstate = '08006'  # connection_failure
                raise error

            return [{"id": 1, "name": "test"}]

        result = await execute_query()

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert call_count == 2


class TestRetryStatistics:
    """Test retry statistics tracking."""

    def test_get_retry_stats(self):
        """Test getting retry statistics."""
        reset_retry_stats()
        stats = get_retry_stats()

        assert isinstance(stats, dict)
        assert "total_operations" in stats
        assert "failed_operations" in stats
        assert "retried_operations" in stats
        assert "total_retries" in stats
        assert "success_rate" in stats

    def test_reset_retry_stats(self):
        """Test resetting retry statistics."""
        reset_retry_stats()
        stats = get_retry_stats()

        assert stats["total_operations"] == 0
        assert stats["failed_operations"] == 0
        assert stats["retried_operations"] == 0
        assert stats["total_retries"] == 0


class TestErrorCodeCoverage:
    """Test coverage of PostgreSQL error codes."""

    @pytest.mark.parametrize("sqlstate", [
        '08000',  # connection_exception
        '08003',  # connection_does_not_exist
        '08006',  # connection_failure
        '40001',  # serialization_failure
        '40P01',  # deadlock_detected
        '53300',  # too_many_connections
        '57P01',  # admin_shutdown
    ])
    def test_all_transient_sqlstates_detected(self, sqlstate):
        """Test that all documented transient SQL states are detected."""
        error = asyncpg.PostgresError()
        error.sqlstate = sqlstate

        assert is_transient_error(error), f"SQL state {sqlstate} should be detected as transient"


class TestEdgeCases:
    """Test edge cases and corner conditions."""

    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """Test behavior with max_retries=0."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=0))
        async def no_retry_operation():
            nonlocal call_count
            call_count += 1
            raise asyncpg.ConnectionFailureError("connection failed")

        with pytest.raises(asyncpg.ConnectionFailureError):
            await no_retry_operation()

        assert call_count == 1  # Only initial attempt, no retries

    @pytest.mark.asyncio
    async def test_very_large_delay(self):
        """Test that very large delays are handled correctly."""
        config = RetryConfig(
            base_delay=1000.0,
            exponential_base=10.0,
            max_delay=2000.0,
            jitter=False
        )

        # Even with huge multipliers, should be capped at max_delay
        delay = calculate_delay(10, config)
        assert delay == 2000.0

    @pytest.mark.asyncio
    async def test_concurrent_retries(self):
        """Test that multiple concurrent operations can retry independently."""
        @with_retry(RetryConfig(max_retries=2, base_delay=0.01))
        async def operation(op_id: int, should_fail: bool):
            if should_fail:
                raise asyncpg.ConnectionFailureError("connection failed")
            return op_id

        # Run multiple operations concurrently
        results = await asyncio.gather(
            operation(1, False),
            operation(2, False),
            operation(3, False),
            return_exceptions=False
        )

        assert results == [1, 2, 3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
