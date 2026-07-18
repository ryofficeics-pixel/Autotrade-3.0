"""
Unit tests for AI infrastructure (Phase 1)
"""
import pytest
import asyncio
from ai.config import get_config, reload_config
from ai.providers.openai_compat import OpenAICompatClient, Message
from ai.router.health_tracker import HealthTracker
from ai.cache.response_cache import ResponseCache


def test_config_loads():
    """Test configuration loads successfully"""
    config = get_config()
    assert config.ai.enabled is not None
    assert config.ai.mode in ["legacy", "hybrid", "ai_full"]
    assert config.ai.models.filter.primary is not None
    print(f"✓ Config loaded: mode={config.ai.mode}, enabled={config.ai.enabled}")


def test_health_tracker():
    """Test health tracker records success and failure"""
    tracker = HealthTracker(auto_disable_threshold=3)
    
    # Record successes
    tracker.record_success("test-model", latency_ms=100)
    tracker.record_success("test-model", latency_ms=200)
    
    health = tracker.get_health("test-model")
    assert health.total_calls == 2
    assert health.successful_calls == 2
    assert health.is_enabled
    assert health.avg_latency_ms == 150
    
    # Record failures
    tracker.record_failure("test-model", "timeout")
    tracker.record_failure("test-model", "timeout")
    tracker.record_failure("test-model", "timeout")
    
    health = tracker.get_health("test-model")
    assert health.failed_calls == 3
    assert health.consecutive_failures == 3
    assert not health.is_enabled  # auto-disabled after 3 failures
    
    print(f"✓ Health tracker working: {health.to_dict()}")


def test_response_cache():
    """Test response cache stores and retrieves"""
    cache = ResponseCache(default_ttl_seconds=60)
    
    key = "test-key"
    response = {"content": "test response"}
    
    # Set and get
    cache.set(key, response, ttl_seconds=60)
    cached = cache.get(key)
    
    assert cached == response
    
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0
    
    # Test miss
    missing = cache.get("nonexistent")
    assert missing is None
    
    stats = cache.get_stats()
    assert stats["misses"] == 1
    
    print(f"✓ Cache working: {stats}")


@pytest.mark.asyncio
async def test_openai_client_structure():
    """Test OpenAI client can be instantiated (no actual API call)"""
    client = OpenAICompatClient(
        base_url="https://openagentic.id/api/v1",
        api_key="test-key",
        timeout=5
    )
    
    # Just test structure, don't make real call
    assert client.base_url == "https://openagentic.id/api/v1"
    assert client.api_key == "test-key"
    
    # Test message hash
    messages = [
        Message(role="user", content="Hello")
    ]
    hash1 = client.message_hash(messages)
    hash2 = client.message_hash(messages)
    assert hash1 == hash2  # deterministic
    
    await client.close()
    print(f"✓ OpenAI client structure valid")


if __name__ == "__main__":
    print("\n=== Phase 1 AI Infrastructure Tests ===\n")
    
    test_config_loads()
    test_health_tracker()
    test_response_cache()
    asyncio.run(test_openai_client_structure())
    
    print("\n✓ All Phase 1 tests passed!")
