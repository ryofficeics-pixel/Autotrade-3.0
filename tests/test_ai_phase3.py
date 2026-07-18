"""
Phase 3 tests: DeepSeek Filter + auto-reconnect
"""
import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai.filter.deepseek_filter import DeepSeekFilter, TradeSignal, get_filter
from ai.config import get_config


def test_filter_config():
    """Test filter config loads correctly"""
    config = get_config()
    assert config.ai.enabled
    assert config.ai.thresholds.ds_reject == 70
    assert config.ai.thresholds.ds_escalate == 90
    print(f"✓ Filter config: reject<{config.ai.thresholds.ds_reject}, escalate>={config.ai.thresholds.ds_escalate}")


def test_trade_signal_model():
    """Test TradeSignal data model"""
    signal = TradeSignal(
        pair="BTC/USDT",
        price=95000.0,
        regime="bull",
        trend="up",
        volatility="medium",
        volume_change="above",
        rsi=65.0,
        macd="bullish",
        daily_pnl=150.0,
        max_consecutive_losses=0
    )
    assert signal.pair == "BTC/USDT"
    assert signal.summary["price"] == 95000.0
    print(f"✓ TradeSignal model works: {signal.pair} @ ${signal.price}")


async def test_filter_prompt_building():
    """Test filter prompt building without API call"""
    f = get_filter()
    signal = TradeSignal(
        pair="ETH/USDT",
        price=3500.0,
        regime="bull",
        trend="up",
        volatility="medium",
        volume_change="normal",
        rsi=55.0,
        macd="bullish",
        daily_pnl=50.0,
        max_consecutive_losses=1
    )
    prompt = f._build_prompt(signal)
    assert "ETH/USDT" in prompt
    assert "3500" in prompt
    assert "bull" in prompt
    print(f"✓ Filter prompt built ({len(prompt)} chars): {prompt[:80]}...")


def test_filter_result_validation():
    """Test FilterResult model validation"""
    from ai.filter.deepseek_filter import FilterResult
    
    rejected = FilterResult(score=30, reason="Bad setup", reject=True)
    assert rejected.score == 30
    assert rejected.reject == True
    assert not rejected.approved
    
    approved = FilterResult(score=95, reason="Strong trend", reject=False)
    assert approved.score == 95
    assert approved.approved
    
    escalated = FilterResult(score=75, reason="Neutral", reject=False, escalate=True)
    assert escalated.score == 75
    assert not escalated.reject
    assert escalated.escalate
    
    print(f"✓ FilterResult validation: reject={rejected.score}, approve={approved.score}, escalate={escalated.score}")


async def test_filter_integration():
    """Test end-to-end filter using actual model router (may fail if API down)"""
    config = get_config()
    
    if not config.ai.enabled:
        print("  Skipping: AI not enabled")
        return
    
    f = get_filter()
    signal = TradeSignal(
        pair="BTC/USDT",
        price=95000.0,
        regime="bull",
        trend="up",
        volatility="medium",
        volume_change="above",
        rsi=65.0,
        macd="bullish",
        daily_pnl=0.0,
        max_consecutive_losses=0
    )
    
    result = await f.evaluate(signal, use_cache=False)
    print(f"✓ Filter evaluated {signal.pair}: score={result.score}, reject={result.reject}, escalate={result.escalate}")
    print(f"  Reason: {result.reason}")
    print(f"  Model: {result.model_used}")
    
    # Test a bad signal
    bad_signal = TradeSignal(
        pair="SOL/USDT",
        price=160.0,
        regime="bear",
        trend="down",
        volatility="high",
        volume_change="below",
        rsi=85.0,
        macd="bearish",
        daily_pnl=-50.0,
        max_consecutive_losses=3
    )
    
    bad_result = await f.evaluate(bad_signal, use_cache=False)
    print(f"✓ Bad signal evaluated: score={bad_result.score}, reject={bad_result.reject}")


if __name__ == "__main__":
    print("\n=== Phase 3: DeepSeek Filter Tests ===\n")
    
    test_filter_config()
    test_trade_signal_model()
    asyncio.run(test_filter_prompt_building())
    test_filter_result_validation()
    asyncio.run(test_filter_integration())
    
    print("\n✓ Phase 3 tests complete!")
