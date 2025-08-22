#!/usr/bin/env python3
"""
Network utilities with aiohttp, SSRF protection, and rate limiting
"""

import aiohttp
import asyncio
import ipaddress
import logging
from urllib.parse import urlparse
from typing import Dict, Set, Optional, Tuple
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# SSRF Protection - blocked networks
BLOCKED_NETWORKS = [
    ipaddress.IPv4Network('127.0.0.0/8'),      # localhost
    ipaddress.IPv4Network('10.0.0.0/8'),       # private
    ipaddress.IPv4Network('172.16.0.0/12'),    # private
    ipaddress.IPv4Network('192.168.0.0/16'),   # private
    ipaddress.IPv4Network('169.254.0.0/16'),   # link-local
    ipaddress.IPv4Network('224.0.0.0/4'),      # multicast
    ipaddress.IPv6Network('::1/128'),          # localhost
    ipaddress.IPv6Network('fc00::/7'),         # private
    ipaddress.IPv6Network('fe80::/10'),        # link-local
]

# Global rate limiter
user_requests: Dict[int, deque] = defaultdict(lambda: deque(maxlen=60))  # Store last 60 requests
MAX_REQUESTS_PER_MINUTE = 20

class SSRFError(Exception):
    """Raised when SSRF protection blocks a request"""
    pass

class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""
    pass

def check_ssrf_protection(url: str) -> None:
    """
    Check if URL is safe from SSRF attacks
    
    Args:
        url: URL to check
        
    Raises:
        SSRFError: If URL is blocked by SSRF protection
    """
    try:
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in ('http', 'https'):
            raise SSRFError(f"Blocked scheme: {parsed.scheme}")
        
        # Check hostname
        hostname = parsed.hostname
        if not hostname:
            raise SSRFError("No hostname in URL")
        
        # Try to resolve to IP
        try:
            import socket
            ip_str = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(ip_str)
            
            # Check against blocked networks
            for network in BLOCKED_NETWORKS:
                if ip in network:
                    raise SSRFError(f"Blocked IP {ip} in network {network}")
                    
        except socket.gaierror:
            # DNS resolution failed - could be legitimate external service
            # Allow it but log
            logger.warning(f"DNS resolution failed for {hostname}")
            
    except Exception as e:
        if isinstance(e, SSRFError):
            raise
        logger.warning(f"SSRF check error for {url}: {e}")

def check_rate_limit(user_id: int) -> None:
    """
    Check if user has exceeded rate limit
    
    Args:
        user_id: User ID to check
        
    Raises:
        RateLimitError: If rate limit exceeded
    """
    now = time.time()
    user_queue = user_requests[user_id]
    
    # Remove old requests (older than 1 minute)
    while user_queue and user_queue[0] < now - 60:
        user_queue.popleft()
    
    # Check rate limit
    if len(user_queue) >= MAX_REQUESTS_PER_MINUTE:
        raise RateLimitError(f"Rate limit exceeded: {len(user_queue)}/{MAX_REQUESTS_PER_MINUTE} requests per minute")
    
    # Add current request
    user_queue.append(now)

class NetworkSession:
    """Shared aiohttp session with security and timeout controls"""
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector_timeout = aiohttp.ClientTimeout(
            total=60,      # Total timeout
            connect=30,    # Connection timeout
            sock_read=30   # Socket read timeout
        )
        
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create shared session"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._connector_timeout,
                headers={
                    'User-Agent': 'TelegramSummarizerBot/1.0'
                }
            )
            
        return self._session
    
    async def close(self):
        """Close session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get(self, url: str, user_id: int = 0, max_size: int = 10*1024*1024, **kwargs) -> Tuple[str, int]:
        """
        Safe GET request with SSRF protection and size limits
        
        Args:
            url: URL to fetch
            user_id: User ID for rate limiting
            max_size: Maximum response size in bytes
            **kwargs: Additional aiohttp parameters
            
        Returns:
            Tuple of (content, status_code)
            
        Raises:
            SSRFError: If URL blocked by SSRF protection
            RateLimitError: If rate limit exceeded
            aiohttp.ClientError: For HTTP errors
        """
        # Security checks
        check_ssrf_protection(url)
        if user_id:
            check_rate_limit(user_id)
        
        session = await self.get_session()
        
        try:
            async with session.get(url, **kwargs) as response:
                # Check content length
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > max_size:
                    raise aiohttp.ClientError(f"Response too large: {content_length} bytes")
                
                # Read with size limit
                content = b""
                async for chunk in response.content.iter_chunked(8192):
                    content += chunk
                    if len(content) > max_size:
                        raise aiohttp.ClientError(f"Response too large: {len(content)} bytes")
                
                return content.decode('utf-8', errors='ignore'), response.status
                
        except asyncio.TimeoutError:
            raise aiohttp.ClientError("Request timeout")

# Global session instance
_global_session = NetworkSession()

async def safe_get(url: str, user_id: int = 0, **kwargs) -> Tuple[str, int]:
    """
    Convenience function for safe HTTP GET
    
    Args:
        url: URL to fetch
        user_id: User ID for rate limiting 
        **kwargs: Additional parameters
        
    Returns:
        Tuple of (content, status_code)
    """
    return await _global_session.get(url, user_id=user_id, **kwargs)

async def cleanup_session():
    """Cleanup global session"""
    await _global_session.close()