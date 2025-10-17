"""Retry utilities for RENTA library.

Provides retry logic with exponential backoff and jitter for handling
transient failures in network operations and external API calls.
"""

import time
import random
import functools
from typing import Optional, Callable, Tuple
import requests
import structlog

logger = structlog.get_logger(__name__)


class RetryConfig:
    """Configuration for retry logic with exponential backoff."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        backoff_factor: float = 0.3,
    ):
        """Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds before first retry
            max_delay: Maximum delay in seconds between retries
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to delays
            backoff_factor: Backoff factor for delay calculation
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.backoff_factor = backoff_factor

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
        if self.jitter:
            # Add jitter: 50-100% of calculated delay
            delay *= 0.5 + random.random() * 0.5
        return delay

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if operation should be retried based on exception and attempt count.

        Args:
            exception: The exception that occurred
            attempt: Current attempt number (0-indexed)

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_attempts:
            return False

        # Define retryable exceptions
        retryable_exceptions = (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError,
            ConnectionError,
            TimeoutError,
        )

        # Check for specific HTTP status codes that should be retried
        if isinstance(exception, requests.exceptions.HTTPError):
            if hasattr(exception, "response") and exception.response is not None:
                status_code = exception.response.status_code
                # Retry on server errors and rate limiting
                if status_code in [429, 500, 502, 503, 504]:
                    return True
                # Don't retry on client errors (4xx except 429)
                if 400 <= status_code < 500:
                    return False

        return isinstance(exception, retryable_exceptions)

    def get_retry_after_delay(self, response) -> Optional[float]:
        """Extract Retry-After header value from HTTP response.

        Args:
            response: HTTP response object

        Returns:
            Retry-After delay in seconds, or None if header not present
        """
        if hasattr(response, "headers") and "Retry-After" in response.headers:
            try:
                return float(response.headers["Retry-After"])
            except (ValueError, TypeError):
                pass
        return None


def with_retry(
    retry_config: Optional[RetryConfig] = None,
    retryable_exceptions: Optional[Tuple] = None,
    logger_instance: Optional[structlog.BoundLogger] = None,
):
    """Decorator to add retry logic to functions.

    Args:
        retry_config: RetryConfig instance, uses default if None
        retryable_exceptions: Tuple of exception types to retry on (deprecated, use retry_config.should_retry)
        logger_instance: Logger instance for retry logging

    Returns:
        Decorated function with retry logic

    Example:
        @with_retry(retry_config=RetryConfig(max_attempts=5))
        def fetch_data():
            return requests.get("https://api.example.com/data")
    """
    if retry_config is None:
        retry_config = RetryConfig()

    if retryable_exceptions is None:
        retryable_exceptions = (
            requests.exceptions.RequestException,
            ConnectionError,
            TimeoutError,
        )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            func_logger = logger_instance or logger

            for attempt in range(retry_config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if we should retry this exception
                    if not retry_config.should_retry(e, attempt):
                        func_logger.error(
                            f"Non-retryable error in {func.__name__}",
                            error=str(e),
                            error_type=type(e).__name__,
                            attempt=attempt + 1,
                        )
                        raise

                    # Don't retry on last attempt
                    if attempt == retry_config.max_attempts - 1:
                        break

                    # Calculate delay
                    delay = retry_config.calculate_delay(attempt)

                    # Check for Retry-After header
                    if hasattr(e, "response"):
                        retry_after = retry_config.get_retry_after_delay(e.response)
                        if retry_after:
                            delay = max(delay, retry_after)

                    func_logger.warning(
                        f"Retrying {func.__name__} after error",
                        error=str(e),
                        error_type=type(e).__name__,
                        attempt=attempt + 1,
                        max_attempts=retry_config.max_attempts,
                        delay_seconds=round(delay, 2),
                    )

                    time.sleep(delay)

            # All retries exhausted
            func_logger.error(
                f"All retries exhausted for {func.__name__}",
                final_error=str(last_exception),
                error_type=type(last_exception).__name__,
                total_attempts=retry_config.max_attempts,
            )
            raise last_exception

        return wrapper

    return decorator
