#!/usr/bin/env python3
"""
Advanced rate limiting with aiolimiter and backoff/circuit breaker
"""

import asyncio
import logging
import time
from typing import Dict, Optional
from collections import defaultdict, deque
from aiolimiter import AsyncLimiter
from config import config

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """Circuit breaker for external services"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half-open
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        
        if self.state == 'open':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'half-open'
                logger.info("Circuit breaker transitioning to half-open")
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = await func(*args, **kwargs)
            
            if self.state == 'half-open':
                self.state = 'closed'
                self.failure_count = 0
                logger.info("Circuit breaker closed - service recovered")
            
            return result
            
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = 'open'
                logger.warning(
                    f"Circuit breaker opened after {self.failure_count} failures"
                )
            
            raise e

class ExponentialBackoff:
    """Exponential backoff for retrying failed requests"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def retry(self, func, *args, **kwargs):
        """Execute function with exponential backoff"""
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            
            except Exception as e:
                last_exception = e
                
                # Check if this is a retryable error
                if hasattr(e, 'status') and e.status in [429, 500, 502, 503, 504]:
                    if attempt < self.max_retries:
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                        logger.warning(
                            f"Retrying after {delay}s (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                        )
                        await asyncio.sleep(delay)
                        continue
                
                # Non-retryable error or max retries reached
                raise e
        
        raise last_exception

class RateLimiter:
    """Advanced rate limiter with per-user and global limits"""
    
    def __init__(self):
        # Global rate limiter
        self.global_limiter = AsyncLimiter(config.GLOBAL_QPS_LIMIT, 1.0)
        
        # Per-user rate limiters
        self.user_limiters: Dict[int, AsyncLimiter] = {}
        
        # Request tracking for sliding window
        self.user_requests: Dict[int, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Circuit breakers for external services
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Backoff handlers
        self.backoff_handler = ExponentialBackoff()
    
    async def acquire_user_limit(self, user_id: int) -> bool:
        """Acquire rate limit for specific user"""
        
        # Check sliding window for per-minute limit
        now = time.time()
        user_queue = self.user_requests[user_id]
        
        # Remove old requests (older than 1 minute)
        while user_queue and user_queue[0] < now - 60:
            user_queue.popleft()
        
        # Check if limit exceeded
        if len(user_queue) >= config.MAX_REQUESTS_PER_MINUTE:
            logger.warning(
                f"Rate limit exceeded for user {user_id}: "
                f"{len(user_queue)}/{config.MAX_REQUESTS_PER_MINUTE} requests/minute"
            )
            return False
        
        # Add current request
        user_queue.append(now)
        
        # Get or create per-user limiter (more granular control)
        if user_id not in self.user_limiters:
            # Allow 5 requests per second per user
            self.user_limiters[user_id] = AsyncLimiter(5, 1.0)
        
        # Acquire both global and user limits
        async with self.global_limiter:
            async with self.user_limiters[user_id]:
                return True
    
    async def external_call_with_protection(self, service_name: str, func, *args, **kwargs):
        """Make external call with circuit breaker and backoff"""
        
        # Get or create circuit breaker for service
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        
        circuit_breaker = self.circuit_breakers[service_name]
        
        # Execute with circuit breaker and backoff
        async def protected_call():
            return await circuit_breaker.call(func, *args, **kwargs)
        
        return await self.backoff_handler.retry(protected_call)
    
    def get_service_status(self, service_name: str) -> Dict:
        """Get status of a specific service's circuit breaker"""
        if service_name in self.circuit_breakers:
            cb = self.circuit_breakers[service_name]
            return {
                'state': cb.state,
                'failure_count': cb.failure_count,
                'last_failure_time': cb.last_failure_time
            }
        return {'state': 'unknown'}
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get rate limiting stats for a user"""
        user_queue = self.user_requests[user_id]
        now = time.time()
        
        # Count recent requests
        recent_requests = [req for req in user_queue if req > now - 60]
        
        return {
            'requests_last_minute': len(recent_requests),
            'requests_limit': config.MAX_REQUESTS_PER_MINUTE,
            'has_dedicated_limiter': user_id in self.user_limiters
        }

# Global rate limiter instance
rate_limiter = RateLimiter()

async def with_rate_limit(user_id: int, func, *args, **kwargs):
    """Execute function with rate limiting"""
    if not await rate_limiter.acquire_user_limit(user_id):
        raise Exception("Rate limit exceeded")
    
    return await func(*args, **kwargs)

async def external_call(service_name: str, func, *args, **kwargs):
    """Execute external call with protection"""
    return await rate_limiter.external_call_with_protection(
        service_name, func, *args, **kwargs
    )