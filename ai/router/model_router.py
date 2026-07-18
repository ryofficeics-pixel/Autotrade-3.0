"""
Model Router with Multi-Layer Failover
Orchestrates primary → fallback → emergency → legacy transitions
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from ai.cache.response_cache import get_response_cache
from ai.config import get_config
from ai.providers.openai_compat import (
    ChatResponse,
    LLMProviderError,
    Message,
    OpenAICompatClient,
)
from ai.router.health_tracker import get_health_tracker

logger = logging.getLogger("ai.router.model_router")


class ModelRouter:
    """
    Multi-layer model router with automatic failover
    
    Flow:
        Filter:    DeepSeek Pro → DeepSeek Free → legacy
        Reasoning: Sonnet → DeepSeek Pro → DeepSeek Free → legacy
    
    Features:
    - Health-aware routing (skips unhealthy models)
    - Response caching
    - Automatic fallback on failure
    - Latency tracking
    - Structured logging
    
    Usage:
        router = ModelRouter()
        
        # Try filter
        response = await router.call(
            call_type="filter",
            messages=[Message(role="user", content="Should I trade?")]
        )
        
        # Try reasoning
        response = await router.call(
            call_type="reasoning",
            messages=[Message(role="system", content="..."), ...]
        )
    """
    
    def __init__(
        self,
        client: OpenAICompatClient | None = None,
        enable_cache: bool = True
    ):
        """
        Initialize model router
        
        Args:
            client: OpenAI-compatible client (created from config if None)
            enable_cache: Whether to use response cache
        """
        self.config = get_config()
        
        if client is None:
            self.client = OpenAICompatClient(
                base_url=self.config.ai.llm.base_url,
                api_key=self.config.ai.llm.api_key,
                timeout=self.config.ai.timeout
            )
        else:
            self.client = client
        
        self.health_tracker = get_health_tracker()
        self.cache = get_response_cache() if enable_cache else None
    
    def _get_model_chain(
        self,
        call_type: Literal["filter", "reasoning"]
    ) -> list[str]:
        if call_type == "filter":
            return [
                self.config.ai.models.filter.primary,
                self.config.ai.models.filter.fallback,
            ]
        elif call_type == "reasoning":
            return [
                self.config.ai.models.reasoning.primary,
                self.config.ai.models.reasoning.fallback_1,
            ]
        else:
            raise ValueError(f"Unknown call_type: {call_type}")
    
    async def call(
        self,
        call_type: Literal["filter", "reasoning"],
        messages: list[Message] | list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        use_cache: bool = True
    ) -> ChatResponse | None:
        """
        Call AI with automatic fallback
        
        Args:
            call_type: "filter" or "reasoning"
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            response_format: Response format spec
            use_cache: Whether to use cache
        
        Returns:
            ChatResponse or None if all models failed (fallback to legacy)
        """
        # Check cache first
        if use_cache and self.cache:
            cache_key = self.cache._generate_key(
                model=call_type,  # use call_type as cache key prefix
                messages=messages,
                temperature=temperature
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info(f"Cache hit for {call_type}")
                return cached
        
        # Get model chain
        model_chain = self._get_model_chain(call_type)
        
        # Try each model in order
        for i, model_name in enumerate(model_chain):
            # Skip unhealthy models
            if not self.health_tracker.is_healthy(model_name):
                logger.warning(f"Skipping unhealthy model: {model_name}")
                continue
            
            logger.info(f"Trying {model_name} for {call_type} (attempt {i+1}/{len(model_chain)})")
            
            start_time = time.time()
            try:
                response = await self.client.chat(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format
                )
                
                latency_ms = (time.time() - start_time) * 1000
                self.health_tracker.record_success(model_name, latency_ms)
                
                logger.info(f"{model_name} succeeded ({latency_ms:.0f}ms)")
                
                # Cache response
                if use_cache and self.cache:
                    self.cache.set(cache_key, response)
                
                return response
            
            except LLMProviderError as e:
                latency_ms = (time.time() - start_time) * 1000
                reason = type(e).__name__
                self.health_tracker.record_failure(model_name, reason)
                
                logger.error(f"{model_name} failed ({reason}, {latency_ms:.0f}ms): {e}")
                
                # Continue to next model
                continue
        
        # All models failed → fallback to legacy
        logger.error(f"All AI models failed for {call_type}, falling back to legacy mode")
        return None
    async def close(self):
        """Close HTTP client"""
        await self.client.close()
    
    async def health_check(self) -> dict[str, Any]:
        """
        Test primary model and re-enable healthy ones.

        Only tests the primary filter model to conserve daily API quota.
        """
        from ai.providers.openai_compat import Message as M

        results = {"models_tested": [], "healthy_count": 0, "total": 1}
        test_message = [M(role="user", content="Health check. Reply OK.")]

        model_name = self.config.ai.models.filter.primary
        self.health_tracker.enable_model(model_name)

        try:
            response = await self.client.chat(
                model=model_name,
                messages=test_message,
                max_tokens=10,
                temperature=0.1,
            )
            success = response is not None and bool(response.content.strip())
            results["models_tested"].append({
                "model": model_name,
                "success": success,
                "error": None,
            })
            if success:
                results["healthy_count"] += 1
                latency = self.health_tracker.get_health(model_name)
                logger.info(f"Health check: {model_name} OK ({latency.avg_latency_ms:.0f}ms avg)")
            else:
                self.health_tracker.record_failure(model_name, "empty_response")
                logger.warning(f"Health check: {model_name} returned empty response")
        except Exception as e:
            self.health_tracker.record_failure(model_name, type(e).__name__)
            results["models_tested"].append({
                "model": model_name,
                "success": False,
                "error": str(e),
            })
            logger.warning(f"Health check: {model_name} FAILED: {e}")

        results["healthy"] = results["healthy_count"] > 0
        return results


    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Global router instance
_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    """Get global router instance (singleton pattern)"""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
