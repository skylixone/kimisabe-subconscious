"""Retry utilities with exponential backoff.

Protects against:
- Network blips
- Temporary API outages
- Rate limiting (429)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd
    retryable_status_codes: set[int] = None
    
    def __post_init__(self):
        if self.retryable_status_codes is None:
            # 429 = rate limit, 502/503/504 = gateway errors
            self.retryable_status_codes = {429, 502, 503, 504}


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay with exponential backoff and jitter."""
    # Exponential: base * (2 ^ attempt)
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)
    
    if config.jitter:
        # Add 0-50% random jitter
        delay = delay * (1 + random.random() * 0.5)
    
    return delay


def with_retry(
    func: Callable[[], T],
    config: RetryConfig | None = None,
    is_retryable: Callable[[Exception], bool] | None = None,
    on_retry: Callable[[Exception, int, float], None] | None = None,
) -> T:
    """Execute a function with retry logic.
    
    Args:
        func: Function to execute
        config: Retry configuration
        is_retryable: Optional function to determine if error is retryable
        on_retry: Optional callback(error, attempt_number, next_delay_seconds)
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries exhausted
    """
    config = config or RetryConfig()
    last_error = None
    
    for attempt in range(config.max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            
            # Check if we should retry this error
            if is_retryable and not is_retryable(e):
                raise
            
            # Check if this is the last attempt
            if attempt >= config.max_retries:
                raise
            
            # Calculate and apply delay
            delay = calculate_delay(attempt, config)
            
            if on_retry:
                on_retry(e, attempt + 1, delay)
            
            time.sleep(delay)
    
    # Should never reach here, but just in case
    raise last_error or RuntimeError("Retry logic failed")


class RetryableLettaClient:
    """Wrapper that adds retry logic to Letta API calls.
    
    Usage:
        client = RetryableLettaClient(base_client)
        result = client.send_message_with_retry(conversation_id, content)
    """
    
    DEFAULT_CONFIG = RetryConfig(
        max_retries=3,
        base_delay=2.0,
        max_delay=30.0,
    )
    
    def __init__(self, client, config: RetryConfig | None = None):
        self.client = client
        self.config = config or self.DEFAULT_CONFIG
    
    def _is_retryable_http_error(self, error: Exception) -> bool:
        """Check if an HTTP error should be retried."""
        import httpx
        
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in self.config.retryable_status_codes
        
        if isinstance(error, httpx.NetworkError):
            return True  # Always retry network errors
        
        if isinstance(error, httpx.TimeoutException):
            return True  # Retry timeouts
        
        return False
    
    def send_message_with_retry(self, conversation_id: str, content: str) -> bool:
        """Send message with retry logic."""
        def _send():
            return self.client.send_message(conversation_id, content)
        
        return with_retry(
            _send,
            config=self.config,
            is_retryable=self._is_retryable_http_error,
        )
    
    def get_messages_with_retry(self, conversation_id: str, **kwargs):
        """Get messages with retry logic."""
        def _get():
            return self.client.get_messages(conversation_id, **kwargs)
        
        return with_retry(
            _get,
            config=self.config,
            is_retryable=self._is_retryable_http_error,
        )
    
    def get_agent_with_retry(self, agent_id: str):
        """Get agent with retry logic."""
        def _get():
            return self.client.get_agent(agent_id)
        
        return with_retry(
            _get,
            config=self.config,
            is_retryable=self._is_retryable_http_error,
        )


# Convenience function for daemon to use
def wrap_letta_client(client):
    """Wrap a LettaClient with retry logic."""
    return RetryableLettaClient(client)
