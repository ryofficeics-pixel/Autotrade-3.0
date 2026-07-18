"""
DeepSeek Filter — Cheap & Fast Trade Signal Filter
Scores signals 0-100, rejects bad trades before expensive reasoning
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai.cache.response_cache import get_response_cache
from ai.config import get_config
from ai.providers.openai_compat import Message
from ai.router.model_router import ModelRouter

logger = logging.getLogger("ai.filter.deepseek_filter")


class TradeSignal(BaseModel):
    """A trade signal to be evaluated by the filter"""
    pair: str
    price: float
    regime: str = "unknown"        # bull / sideways / bear
    trend: str = "neutral"         # up / down / neutral
    volatility: str = "medium"     # low / medium / high
    volume_change: str = "normal"  # below / normal / above
    rsi: float = 50.0
    macd: str = "neutral"          # bullish / bearish / neutral
    daily_pnl: float = 0.0
    max_consecutive_losses: int = 0
    
    @property
    def summary(self) -> dict[str, Any]:
        """Compressed feature summary for the prompt"""
        return self.model_dump()


class FilterResult(BaseModel):
    """Filter evaluation result"""
    score: int = Field(default=50, ge=0, le=100)
    reason: str = ""
    reject: bool = False   # True = reject this trade
    escalate: bool = False # True = send to reasoning
    model_used: str = ""
    raw_response: str = ""
    
    @property
    def approved(self) -> bool:
        """Trade is approved (not rejected)"""
        return not self.reject


class DeepSeekFilter:
    """
    Cheap trade signal filter using fast/cheap models
    
    Flow:
        1. Receive TradeSignal
        2. Compress to feature summary
        3. Call model (DeepSeek Pro → DeepSeek Free → fallback)
        4. Parse JSON response
        5. Apply thresholds from config
        6. Return FilterResult
    
    Config thresholds:
        ds_reject: score < this → auto reject (default: 70)
        ds_escalate: score >= this → auto approve without reasoning (default: 90)
    """
    
    def __init__(self, prompt_path: str | Path | None = None, router=None):
        self.config = get_config()
        self.router = router if router is not None else ModelRouter()
        self.cache = get_response_cache()
        
        # Load prompt template
        if prompt_path is None:
            prompt_path = Path(__file__).parent.parent / "prompts" / "filter_prompt.txt"
        else:
            prompt_path = Path(prompt_path)
        
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self._prompt_template = f.read()
        else:
            self._prompt_template = ""
            logger.warning(f"Filter prompt not found at {prompt_path}")
    
    def _build_prompt(self, signal: TradeSignal) -> str:
        """Fill prompt template with signal data"""
        if not self._prompt_template:
            # Fallback inline prompt
            return (
                f"Evaluate trade: {signal.pair} @ ${signal.price:.2f}, "
                f"regime={signal.regime}, trend={signal.trend}, "
                f"RSI={signal.rsi:.0f}, MACD={signal.macd}, "
                f"volume={signal.volume_change}, volatility={signal.volatility}, "
                f"daily_pnl=${signal.daily_pnl:.2f}, "
                f"consecutive_losses={signal.max_consecutive_losses}. "
                f"Score 0-100, reject if < 70."
            )
        
        return self._prompt_template.format(
            pair=signal.pair,
            price=f"{signal.price:.2f}",
            regime=signal.regime,
            trend=signal.trend,
            volatility=signal.volatility,
            volume_change=signal.volume_change,
            rsi=f"{signal.rsi:.0f}",
            macd=signal.macd,
            daily_pnl=f"{signal.daily_pnl:.2f}",
            max_consecutive_losses=signal.max_consecutive_losses,
            REJECT_THRESHOLD=self.config.ai.thresholds.ds_reject,
            ESCALATE_THRESHOLD=self.config.ai.thresholds.ds_escalate,
        )
    
    async def evaluate(
        self,
        signal: TradeSignal,
        use_cache: bool = True
    ) -> FilterResult:
        """
        Evaluate a trade signal through the filter chain
        
        Args:
            signal: Trade signal to evaluate
            use_cache: Whether to use response cache
        
        Returns:
            FilterResult with score, decision, and reasoning
        """
        prompt = self._build_prompt(signal)
        reject_threshold = self.config.ai.thresholds.ds_reject
        escalate_threshold = self.config.ai.thresholds.ds_escalate
        
        logger.info(f"Filter evaluating {signal.pair} (RSI={signal.rsi:.0f}, trend={signal.trend})")
        
        # Call model router with filter call type
        response = await self.router.call(
            call_type="filter",
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,  # low temperature for consistent scoring
            max_tokens=150,
            response_format={"type": "json_object"},
            use_cache=use_cache
        )
        
        # Parse response
        result = FilterResult()
        
        if response is None:
            # All models failed — let trade through (fail open)
            logger.warning("Filter unavailable — allowing trade (fail-open)")
            result.score = 50
            result.reason = "Filter unavailable — allowing trade"
            result.reject = False
            result.escalate = True
            return result
        
        result.raw_response = response.content
        result.model_used = response.model
        
        try:
            data = response.parse_json()
            result.score = int(data.get("score", 50))
            result.reason = data.get("reason", "")
            
            # Clamp score to 0-100
            result.score = max(0, min(100, result.score))
            
            # Apply threshold logic
            if result.score < reject_threshold:
                result.reject = True
                result.escalate = False
                logger.info(f"Filter REJECTED {signal.pair} (score={result.score} < {reject_threshold}): {result.reason}")
            elif result.score >= escalate_threshold:
                result.reject = False
                result.escalate = False
                logger.info(f"Filter APPROVED {signal.pair} (score={result.score} >= {escalate_threshold}): {result.reason}")
            else:
                result.reject = False
                result.escalate = True
                logger.info(f"Filter ESCALATED {signal.pair} (score={result.score}): {result.reason}")
        
        except Exception as e:
            logger.error(f"Failed to parse filter response: {e}")
            result.score = 50
            result.reason = f"Parse error: {e}"
            result.reject = False
            result.escalate = True  # escalate on error
        
        return result


# Global filter instance
_filter: DeepSeekFilter | None = None


def get_filter() -> DeepSeekFilter:
    """Get global filter instance (singleton pattern)"""
    global _filter
    if _filter is None:
        _filter = DeepSeekFilter()
    return _filter
