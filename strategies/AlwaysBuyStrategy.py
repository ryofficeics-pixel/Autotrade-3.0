from pandas import DataFrame
from freqtrade.strategy import IStrategy


class AlwaysBuyStrategy(IStrategy):
    minimal_roi = {"0": 0.02, "20": 0.015, "40": 0.01}
    stoploss = -0.015
    timeframe = "5m"
    process_only_new_candles = False
    use_exit_signal = True
    startup_candle_count = 0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["volume"] >= 0), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
