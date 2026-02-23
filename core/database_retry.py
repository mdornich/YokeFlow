"""
Database Retry Logic with Exponential Backoff
==============================================

Production-ready retry decorator for database operations with:
- Exponential backoff with jitter
- Configurable max retries and timeouts
- Transient error detection
- Comprehensive logging
- Type safety

Usage:
    from core.database_retry import with_retry, RetryConfig

    @with_retry()
    async def my_db_operation():
        async with db.acquire() as conn:
            return await conn.fetchval("SELECT 1")

    # Custom configuration
    @with_retry(RetryConfig(max_retries=5, base_delay=2.0))
    async def critical_operation():
        ...
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from functools import wraps
from typing import Optional, Callable, Any, TypeVar, cast

import asyncpg

logger = logging.getLogger(__name__)

# Type variable for generic function signatures
F = TypeVar('F', bound=Callable[..., Any])


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    """Maximum number of retry attempts (default: 3)"""

    base_delay: float = 1.0
    """Base delay in seconds between retries (default: 1.0)"""

    max_delay: float = 30.0
    """Maximum delay in seconds (caps exponential backoff, default: 30.0)"""

    exponential_base: float = 2.0
    """Exponential backoff multiplier (default: 2.0)"""

    jitter: bool = True
    """Add random jitter to delays to prevent thundering herd (default: True)"""

    jitter_range: float = 0.1
    """Jitter range as fraction of delay (default: 0.1 = ±10%)"""


# PostgreSQL error codes for transient errors that should be retried
# See: https://www.postgresql.org/docs/current/errcodes-appendix.html
TRANSIENT_ERROR_CODES = {
    # Connection exceptions
    '08000',  # connection_exception
    '08003',  # connection_does_not_exist
    '08006',  # connection_failure
    '08001',  # sqlclient_unable_to_establish_sqlconnection
    '08004',  # sqlserver_rejected_establishment_of_sqlconnection
    '08007',  # transaction_resolution_unknown
    '08P01',  # protocol_violation

    # System errors
    '53000',  # insufficient_resources
    '53100',  # disk_full
    '53200',  # out_of_memory
    '53300',  # too_many_connections
    '53400',  # configuration_limit_exceeded

    # Transaction errors
    '40001',  # serialization_failure
    '40P01',  # deadlock_detected

    # Operator intervention
    '57000',  # operator_intervention
    '57014',  # query_canceled
    '57P01',  # admin_shutdown
    '57P02',  # crash_shutdown
    '57P03',  # cannot_connect_now
}


def is_transient_error(error: Exception) -> bool:
    """
    Determine if an error is transient and worth retrying.

    Args:
        error: Exception to check

    Returns:
        True if error is transient and should be retried
    """
    # asyncpg PostgresError
    if isinstance(error, asyncpg.PostgresError):
        sqlstate = getattr(error, 'sqlstate', None)
        if sqlstate in TRANSIENT_ERROR_CODES:
            return True

    # Connection/network errors
    if isinstance(error, (
        asyncpg.ConnectionDoesNotExistError,
        asyncpg.ConnectionFailureError,
        asyncpg.InterfaceError,
        asyncpg.CannotConnectNowError,
        asyncpg.TooManyConnectionsError,
    )):
        return True

    # Check error message for common transient patterns
    error_msg = str(error).lower()
    transient_patterns = [
        'connection refused',
        'connection reset',
        'connection timeout',
        'connection closed',
        'broken pipe',
        'network error',
        'temporary failure',
        'too many connections',
        'deadlock',
        'serialization failure',
    ]

    for pattern in transient_patterns:
        if pattern in error_msg:
            return True

    return False


def calculate_delay(
    attempt: int,
    config: RetryConfig,
    error: Optional[Exception] = None
) -> float:
    """
    Calculate retry delay with exponential backoff and optional jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration
        error: Optional error for context

    Returns:
        Delay in seconds before next retry
    """
    # Calculate exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = config.base_delay * (config.exponential_base ** attempt)

    # Cap at max_delay
    delay = min(delay, config.max_delay)

    # Add jitter if enabled
    if config.jitter:
        jitter_amount = delay * config.jitter_range
        delay = delay + random.uniform(-jitter_amount, jitter_amount)

    # Ensure non-negative
    return max(0.0, delay)


def with_retry(config: Optional[RetryConfig] = None) -> Callable[[F], F]:
    """
    Decorator to add retry logic with exponential backoff to async functions.

    Args:
        config: Optional retry configuration (uses defaults if None)

    Returns:
        Decorated function with retry logic

    Example:
        @with_retry()
        async def fetch_data():
            async with db.acquire() as conn:
                return await conn.fetchval("SELECT 1")

        @with_retry(RetryConfig(max_retries=5, base_delay=2.0))
        async def critical_fetch():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error: Optional[Exception] = None

            for attempt in range(config.max_retries + 1):
                try:
                    # Execute the function
                    result = await func(*args, **kwargs)

                    # Log successful retry if not first attempt
                    if attempt > 0:
                        logger.info(
                            f"Database operation '{func.__name__}' succeeded after {attempt} retries"
                        )

                    return result

                except Exception as error:
                    last_error = error

                    # Check if we should retry
                    if attempt >= config.max_retries:
                        # Max retries exhausted (safe error message extraction)
                        try:
                            error_msg = str(error) if str(error) != '<exception str() failed>' else type(error).__name__
                        except:
                            error_msg = type(error).__name__

                        logger.error(
                            f"Database operation '{func.__name__}' failed after {config.max_retries} retries: {error_msg}"
                        )
                        raise

                    if not is_transient_error(error):
                        # Non-transient error, don't retry (safe error message extraction)
                        try:
                            error_msg = str(error) if str(error) != '<exception str() failed>' else type(error).__name__
                        except:
                            error_msg = type(error).__name__

                        logger.error(
                            f"Database operation '{func.__name__}' failed with non-transient error: {error_msg}"
                        )
                        raise

                    # Calculate delay for next retry
                    delay = calculate_delay(attempt, config, error)

                    # Log retry attempt (safe error message extraction)
                    try:
                        error_msg = str(error) if str(error) != '<exception str() failed>' else type(error).__name__
                    except:
                        error_msg = type(error).__name__

                    logger.warning(
                        f"Database operation '{func.__name__}' failed (attempt {attempt + 1}/{config.max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {error_msg}"
                    )

                    # Wait before retrying
                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            if last_error:
                raise last_error
            else:
                raise RuntimeError(f"Retry logic failed for {func.__name__}")

        return cast(F, wrapper)

    return decorator


async def test_retry_with_connection_pool(pool: asyncpg.Pool, config: Optional[RetryConfig] = None):
    """
    Test helper: Execute a simple query with retry logic.

    Args:
        pool: asyncpg connection pool
        config: Optional retry configuration

    Returns:
        Query result

    Example:
        result = await test_retry_with_connection_pool(db.pool)
    """
    @with_retry(config)
    async def execute_test_query():
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT 1")

    return await execute_test_query()


# Observability: Track retry statistics
class RetryStats:
    """Track retry statistics for monitoring."""

    def __init__(self):
        self.total_operations = 0
        self.failed_operations = 0
        self.retried_operations = 0
        self.total_retries = 0
        self.transient_errors = 0
        self.permanent_errors = 0

    def record_success(self, attempts: int):
        """Record successful operation."""
        self.total_operations += 1
        if attempts > 1:
            self.retried_operations += 1
            self.total_retries += (attempts - 1)

    def record_failure(self, attempts: int, is_transient: bool):
        """Record failed operation."""
        self.total_operations += 1
        self.failed_operations += 1
        self.total_retries += (attempts - 1)

        if is_transient:
            self.transient_errors += 1
        else:
            self.permanent_errors += 1

    def get_stats(self) -> dict:
        """Get statistics dictionary."""
        return {
            'total_operations': self.total_operations,
            'failed_operations': self.failed_operations,
            'retried_operations': self.retried_operations,
            'total_retries': self.total_retries,
            'transient_errors': self.transient_errors,
            'permanent_errors': self.permanent_errors,
            'success_rate': (
                (self.total_operations - self.failed_operations) / self.total_operations
                if self.total_operations > 0 else 0.0
            ),
            'retry_success_rate': (
                self.retried_operations / (self.retried_operations + self.transient_errors)
                if (self.retried_operations + self.transient_errors) > 0 else 0.0
            ),
        }


# Global stats instance
_global_stats = RetryStats()


def get_retry_stats() -> dict:
    """
    Get global retry statistics.

    Returns:
        Dictionary with retry statistics
    """
    return _global_stats.get_stats()


def reset_retry_stats():
    """Reset global retry statistics."""
    global _global_stats
    _global_stats = RetryStats()
