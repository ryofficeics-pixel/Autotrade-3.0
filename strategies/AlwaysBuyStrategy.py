import asyncio
import logging

from pandas import DataFrame
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class AlwaysBuyStrategy(IStrategy):
    minimal_roi = {"0": 0.04}
    stoploss = -0.02

    timeframe = "5m"
    process_only_new_candles = True
    use_exit_signal = True
    startup_candle_count = 50

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe['close']

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, float('nan'))
        dataframe['rsi'] = 100 - (100 / (1 + rs))

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        dataframe['macd'] = macd_line
        dataframe['macd_signal'] = macd_signal
        dataframe['macd_hist'] = macd_line - macd_signal

        dataframe['ema20'] = close.ewm(span=20, adjust=False).mean()
        dataframe['sma50'] = close.rolling(50).mean()

        high, low = dataframe['high'], dataframe['low']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        dataframe['atr'] = tr.rolling(14).mean()

        dataframe['volume_sma'] = dataframe['volume'].rolling(20).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0

        if len(dataframe) < self.startup_candle_count:
            return dataframe

        last = dataframe.iloc[-1]
        pair = metadata['pair']

        atr_pct = last['atr'] / last['close'] if last['close'] > 0 else 0
        regime = 'bull' if last['ema20'] > last['sma50'] else 'bear'
        trend_dir = 'up' if last['ema20'] > last['sma50'] else 'down'
        volatility = 'high' if atr_pct > 0.02 else ('low' if atr_pct < 0.005 else 'medium')
        vol_ratio = last['volume'] / last['volume_sma'] if last['volume_sma'] > 0 else 1
        volume_change = 'above' if vol_ratio > 1.2 else ('below' if vol_ratio < 0.8 else 'normal')
        macd_status = 'bullish' if last['macd_hist'] > 0 else ('bearish' if last['macd_hist'] < 0 else 'neutral')

        from ai.filter.deepseek_filter import TradeSignal
        rsi_raw = last['rsi']
        rsi_val = 50.0 if not (rsi_raw == rsi_raw) else float(rsi_raw)
        signal = TradeSignal(
            pair=pair,
            price=float(last['close']),
            regime=regime,
            trend=trend_dir,
            volatility=volatility,
            volume_change=volume_change,
            rsi=rsi_val,
            macd=macd_status,
            daily_pnl=0.0,
            max_consecutive_losses=0,
        )

        try:
            result = self._run_ai_filter(signal)
            if result is not None and result.reject:
                logger.info(f"AI REJECTED {pair}: score={result.score} reason={result.reason}")
                return dataframe
        except Exception as e:
            logger.warning(f"AI filter error for {pair}: {e} — allowing trade")

        dataframe.loc[dataframe.index[-1], 'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def _run_ai_filter(self, signal):
        from ai.filter.deepseek_filter import DeepSeekFilter
        from ai.router.model_router import ModelRouter

        async def _evaluate():
            f = DeepSeekFilter(router=ModelRouter())
            return await f.evaluate(signal, use_cache=True)

        return asyncio.run(_evaluate())
