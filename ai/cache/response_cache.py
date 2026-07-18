"""
Response Cache System
TTL-based cache for AI responses to reduce token usage and latency
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ai.cache.response_cache")


@dataclass
class CachedResponse:
    """Cached AI response with TTL"""
    key: str
    response: Any
    cached_at: float
    ttl_seconds: int
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        return time.time() - self.cached_at > self.ttl_seconds
    
    @property
    def age_seconds(self) -> int:
        """Age of cache entry in seconds"""
        return int(time.time() - self.cached_at)


class ResponseCache:
    """
    TTL-based cache for AI responses
    
    Features:
    - Configurable TTL per cache entry
    - Automatic expiration
    - Thread-safe operations
    - Cache hit statistics
    - Manual invalidation
    
    Usage:
        cache = ResponseCache(default_ttl_seconds=300)
        
        # Try to get from cache
        response = cache.get(cache_key)
        if response is None:
            # Cache miss - call AI
            response = await ai_call()
            cache.set(cache_key, response, ttl_seconds=300)
        
        # Get stats
        stats = cache.get_stats()
        print(f"Hit rate: {stats['hit_rate']:.1%}")
    """
    
    def __init__(self, default_ttl_seconds: int = 300):
        """
        Initialize response cache
        
        Args:
            default_ttl_seconds: Default TTL for cache entries (5 minutes)
        """
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: dict[str, CachedResponse] = {}
        self._lock = threading.Lock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def _generate_key(
        self,
        model: str,
        messages: list[dict] | str,
        temperature: float = 0.7
    ) -> str:
        """
        Generate cache key from inputs
        
        Args:
            model: Model name
            messages: Messages or prompt string
            temperature: Temperature parameter
        
        Returns:
            Cache key (hex string)
        """
        # Normalize messages
        if isinstance(messages, str):
            content = messages
        else:
            content = json.dumps(messages, sort_keys=True)
        
        # Create hash
        key_str = f"{model}:{temperature}:{content}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]
    
    def get(self, key: str) -> Any | None:
        """
        Get response from cache
        
        Args:
            key: Cache key
        
        Returns:
            Cached response or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                logger.debug(f"Cache miss: {key}")
                return None
            
            entry = self._cache[key]
            
            # Check expiration
            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache expired: {key} (age: {entry.age_seconds}s)")
                return None
            
            self._hits += 1
            logger.debug(f"Cache hit: {key} (age: {entry.age_seconds}s)")
            return entry.response
    
    def set(
        self,
        key: str,
        response: Any,
        ttl_seconds: int | None = None
    ):
        """
        Store response in cache
        
        Args:
            key: Cache key
            response: Response to cache
            ttl_seconds: TTL in seconds (defaults to default_ttl_seconds)
        """
        if ttl_seconds is None:
            ttl_seconds = self.default_ttl_seconds
        
        entry = CachedResponse(
            key=key,
            response=response,
            cached_at=time.time(),
            ttl_seconds=ttl_seconds
        )
        
        with self._lock:
            self._cache[key] = entry
            logger.debug(f"Cached response: {key} (TTL: {ttl_seconds}s)")
    
    def invalidate(self, key: str):
        """
        Invalidate a cache entry
        
        Args:
            key: Cache key
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Invalidated cache: {key}")
    
    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared {count} cache entries")
    
    def prune_expired(self) -> int:
        """
        Remove expired entries
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.info(f"Pruned {len(expired_keys)} expired entries")
            
            return len(expired_keys)
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dict with hit/miss counts, rates, and cache size
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
            
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total_requests,
                "hit_rate": hit_rate,
                "default_ttl_seconds": self.default_ttl_seconds
            }
    
    def reset_stats(self):
        """Reset hit/miss statistics"""
        with self._lock:
            self._hits = 0
            self._misses = 0
            logger.debug("Cache stats reset")


# Global cache instance
_response_cache: ResponseCache | None = None


def get_response_cache() -> ResponseCache:
    """Get global response cache instance (singleton pattern)"""
    global _response_cache
    if _response_cache is None:
        from ai.config import get_config
        config = get_config()
        _response_cache = ResponseCache(
            default_ttl_seconds=config.ai.cache_minutes * 60
        )
    return _response_cache
