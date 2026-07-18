"""
AI Status API Endpoint
Returns current AI system health and activity
"""
from __future__ import annotations

from fastapi import APIRouter

from ai.config import get_config
from ai.router.health_tracker import get_health_tracker
from ai.cache.response_cache import get_response_cache
from ai.router.model_router import get_router
from ai.providers.openai_compat import Message

router = APIRouter()

# Auto-reconnect status (updated by background task)
auto_reconnect_status: dict = {
    "last_check": "—",
    "healthy": False,
    "active_model": ""
}


def update_auto_reconnect(healthy: bool, model: str):
    """Update auto-reconnect status (called from background task)"""
    global auto_reconnect_status
    from datetime import datetime
    auto_reconnect_status = {
        "last_check": datetime.now().strftime("%H:%M:%S"),
        "healthy": healthy,
        "active_model": model
    }


@router.get("/api/ai/status")
async def ai_status():
    """
    Get AI system status
    
    Returns:
        {
          "enabled": bool,
          "mode": "legacy" | "hybrid" | "ai_full",
          "models": { ... },
          "health": { ... },
          "cache": { ... },
          "auto_reconnect": {
            "last_check": str,
            "healthy": bool,
            "active_model": str
          }
        }
    """
    try:
        config = get_config()
        health_tracker = get_health_tracker()
        cache = get_response_cache()
        
        return {
            "enabled": config.ai.enabled,
            "mode": config.ai.mode,
            "models": {
                "filter": {
                    "primary": config.ai.models.filter.primary,
                    "fallback": config.ai.models.filter.fallback,
                    "fallback_2": config.ai.models.filter.fallback_2
                },
                "reasoning": {
                    "primary": config.ai.models.reasoning.primary,
                    "fallback_1": config.ai.models.reasoning.fallback_1,
                    "fallback_2": config.ai.models.reasoning.fallback_2,
                    "fallback_3": config.ai.models.reasoning.fallback_3,
                    "fallback_4": config.ai.models.reasoning.fallback_4
                }
            },
            "health": health_tracker.get_all_health(),
            "cache": cache.get_stats(),
            "auto_reconnect": auto_reconnect_status
        }
    except Exception as e:
        return {
            "enabled": False,
            "mode": "legacy",
            "error": str(e)
        }


@router.post("/api/ai/retry")
async def ai_retry():
    """
    Force AI reconnection by testing each model in the failover chain
    
    Returns:
        {
          "success": bool,
          "tested_models": [{"model": str, "success": bool, "latency_ms": float, "error": str}],
          "fallback_activated": str | None
        }
    """
    try:
        config = get_config()
        health_tracker = get_health_tracker()
        model_router = get_router()
        
        if not config.ai.enabled:
            return {
                "success": False,
                "error": "AI is disabled in config",
                "tested_models": []
            }
        
        # Test filter chain
        filter_models = [
            config.ai.models.filter.primary,
            config.ai.models.filter.fallback
        ]
        
        # Test reasoning chain
        reasoning_models = [
            config.ai.models.reasoning.primary,
            config.ai.models.reasoning.fallback_1,
            config.ai.models.reasoning.fallback_2,
            config.ai.models.reasoning.fallback_3
        ]
        
        all_models = list(set(filter_models + reasoning_models))
        tested = []
        
        # Test each model with a simple health check message
        test_message = [Message(role="user", content="Health check")]
        
        for model in all_models:
            # Re-enable if disabled
            health_tracker.enable_model(model)
            
            # Try calling the model through the router
            try:
                response = await model_router.call(
                    call_type="filter",  # arbitrary
                    messages=test_message,
                    use_cache=False  # force fresh call
                )
                
                health = health_tracker.get_health(model)
                tested.append({
                    "model": model,
                    "success": response is not None,
                    "latency_ms": health.avg_latency_ms if health else 0,
                    "error": None
                })
            except Exception as e:
                tested.append({
                    "model": model,
                    "success": False,
                    "latency_ms": 0,
                    "error": str(e)
                })
        
        # Determine which model is working
        working_model = None
        for test in tested:
            if test["success"]:
                working_model = test["model"]
                break
        
        return {
            "success": working_model is not None,
            "tested_models": tested,
            "fallback_activated": working_model
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "tested_models": []
        }
