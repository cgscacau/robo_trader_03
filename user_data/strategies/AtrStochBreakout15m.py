from freqtrade.strategy.interface import IStrategy
from freqtrade.persistence import Trade
from freqtrade.strategy import IntParameter, DecimalParameter
from pandas import DataFrame
import pandas_ta as pta
import numpy as np


class AtrStochBreakout15m(IStrategy):
    """
    Estratégia:
    - Timeframe: 15m
    - Compra quando:
        * Preço acima da EMA
        * Estocástico abaixo de um limiar
        * Candle atual fecha rompendo o topo do candle anterior
    - Stop = mult_stop * ATR(atr_period)
    - Alvo = mult_tp * ATR(atr_period)
    """

    timeframe = "15m"
    can_short = False

    # Número mínimo de candles para ter todos os indicadores
    startup_candle_count = 200

    # ROI praticamente desativado (saída via custom_exit)
    minimal_roi = {"0": 100.0}

    # Stop genérico de segurança (será sobrescrito pelo custom_stoploss)
    stoploss = -0.99

    # Usaremos stoploss customizado e não usaremos sinais de saída padrão
    use_custom_stoploss = True
    use_exit_signal = False
    exit_profit_only = False

    # ----------------------------
    # Parâmetros otimizáveis (Hyperopt - espaço "buy")
    # ----------------------------
    buy_ema_period = IntParameter(20, 200, default=80, space="buy")
    buy_stoch_low = IntParameter(5, 40, default=20, space="buy")

    buy_atr_period = IntParameter(5, 30, default=10, space="buy")
    buy_atr_tp_mult = DecimalParameter(1.0, 6.0, default=3.0, decimals=1, space="buy")
    buy_atr_sl_mult = DecimalParameter(0.5, 3.0, default=1.5, decimals=1, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calcula EMA, Estocástico e ATR com base nos parâmetros otimizáveis.
        """

        ema_period = int(self.buy_ema_period.value)
        atr_period = int(self.buy_atr_period.value)

        # EMA dinâmica (pandas_ta)
        dataframe["ema"] = pta.ema(dataframe["close"], length=ema_period)

        # Estocástico (pandas_ta)
        stoch = pta.stoch(
            high=dataframe["high"],
            low=dataframe["low"],
            close=dataframe["close"],
            k=14,
            d=3,
            smooth_k=3,
        )
        # Colunas típicas: STOCHk_14_3_3 e STOCHd_14_3_3
        dataframe["stoch_k"] = stoch.iloc[:, 0]
        dataframe["stoch_d"] = stoch.iloc[:, 1]

        # ATR dinâmico (pandas_ta)
        dataframe["atr"] = pta.atr(
            high=dataframe["high"],
            low=dataframe["low"],
            close=dataframe["close"],
            length=atr_period,
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entrada:
        - close > ema
        - stoch_k < stoch_low
        - close rompe o topo do candle anterior (close > high.shift(1))
        """

        stoch_low = float(self.buy_stoch_low.value)

        conditions = []
        conditions.append(dataframe["close"] > dataframe["ema"])
        conditions.append(dataframe["stoch_k"] < stoch_low)
        conditions.append(dataframe["close"] > dataframe["high"].shift(1))

        cond = np.all(conditions, axis=0)

        dataframe["enter_long"] = 0
        dataframe.loc[cond, "enter_long"] = 1
        dataframe.loc[cond, "enter_tag"] = "atr_stoch_breakout"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Saída padrão não utilizada (usamos custom_exit).
        """
        dataframe["exit_long"] = 0
        return dataframe

    # ----------------------------
    # Helpers de ATR por trade
    # ----------------------------

    def _get_atr_for_trade(self, pair: str, trade: Trade):
        """
        Busca o valor de ATR no candle onde o trade foi aberto.
        """
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        df_trade = df.loc[df["date"] <= trade.open_date_utc]
        if df_trade.empty:
            return None

        atr = df_trade.iloc[-1]["atr"]
        return atr

    # ----------------------------
    # Stoploss customizado (mult * ATR, por padrão 1.5)
    # ----------------------------

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        Stop = mult_stop * ATR / preço de entrada (valor negativo em %).
        """
        atr = self._get_atr_for_trade(pair, trade)
        if atr is None or trade.open_rate == 0:
            return self.stoploss  # fallback

        mult_sl = float(self.buy_atr_sl_mult.value)

        sl_pct = mult_sl * atr / trade.open_rate
        return -float(sl_pct)

    # ----------------------------
    # Take Profit customizado (mult * ATR, por padrão 3.0)
    # ----------------------------

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        """
        Take Profit = mult_tp * ATR / preço de entrada.
        Quando o lucro atual (%) >= alvo, fecha a posição.
        """
        atr = self._get_atr_for_trade(pair, trade)
        if atr is None or trade.open_rate == 0:
            return None

        mult_tp = float(self.buy_atr_tp_mult.value)

        tp_pct = mult_tp * atr / trade.open_rate

        if current_profit >= tp_pct:
            return "tp_atr_mult"

        return None

