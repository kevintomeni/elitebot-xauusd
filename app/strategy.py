"""EliteBot — stratégie hybride « momentum court terme aligné tendance de fond ».

Unité de décision : M5. Filtre de fond : EMA 200 sur H1.
  • Long uniquement si : prix > EMA200(H1), RSI(M5) remonte sous 45,
    close <= bande basse de Bollinger (pullback), close > EMA20(M5) ou mèche
    de rejet (close > open).
  • Short uniquement si : prix < EMA200(H1), RSI(M5) retombe sous 55+,
    close >= bande haute de Bollinger, close < open ou close < EMA20(M5).
  • Filtre de volatilité : ATR(M5) minimum absolu ET relatif, sinon aucun trade.
  • SL/TP indexés ATR : SL = 1.5×ATR, TP = 3.0×ATR (ratio 1:2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import settings
from .indicators import add_indicators

log = logging.getLogger("elitebot.strategy")


@dataclass
class Signal:
    side: str                      # "buy" | "sell" | "none"
    reason: str
    atr: float
    entry: float
    sl: float
    tp: float


def _trend(df_h1_ind: "pd.DataFrame") -> str:
    """Tendance de fond selon la position du prix vs EMA200 (H1)."""
    last = df_h1_ind.iloc[-1]
    close = float(last["close"])
    ema200 = float(last["ema200"])
    if ema200 != ema200:                     # NaN → historique trop court
        return "neutral"
    if close > ema200 * 1.0005:
        return "up"
    if close < ema200 * 0.9995:
        return "down"
    return "neutral"


def analyze(df_m5: "pd.DataFrame", df_h1: "pd.DataFrame") -> Signal:
    """Point d'entrée de la stratégie : renvoie un Signal complet ou "none"."""
    df = add_indicators(df_m5.tail(120).copy(), settings)
    df_h1i = add_indicators(df_h1.tail(settings.ema_h1_period + 60).copy(), settings)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last["close"])
    atr_val = float(last["atr"])
    rsi_val = float(last["rsi"])
    bb_upper = float(last["bb_upper"])
    bb_lower = float(last["bb_lower"])
    ema200_h1 = float(df_h1i.iloc[-1]["ema200"])

    trend = _trend(df_h1i)

    # --------------------------- Filtre de volatilité (ATR min absolu+relatif)
    ratio = atr_val / price if price > 0 else 0.0
    vol_ok = atr_val >= settings.min_atr and ratio >= settings.min_atr_ratio
    if not vol_ok:
        return Signal("none",
                      f"Volatilité insuffisante (ATR={atr_val:.2f}, ratio={ratio:.5f})",
                      atr_val, price, 0.0, 0.0)

    if trend == "up":
        cond_pullback = price <= bb_lower
        cond_momentum = rsi_val <= 45.0 and rsi_val > prev_rsi(prev)
        cond_confirm = float(last["close"]) > float(last["open"]) or \
            price > float(last["ema_fast"])
        if cond_pullback and cond_momentum and cond_confirm:
            sl = price - settings.sl_atr_mult * atr_val
            tp = price + settings.tp_atr_mult * atr_val
            return Signal("buy", "Pullback haussier RSI+BB aligné EMA200(H1) ↑",
                          atr_val, price, sl, tp)

    if trend == "down":
        cond_pullback = price >= bb_upper
        cond_momentum = rsi_val >= 55.0 and rsi_val < prev_rsi(prev)
        cond_confirm = float(last["close"]) < float(last["open"]) or \
            price < float(last["ema_fast"])
        if cond_pullback and cond_momentum and cond_confirm:
            sl = price + settings.sl_atr_mult * atr_val
            tp = price - settings.tp_atr_mult * atr_val
            return Signal("sell", "Pullback baissier RSI+BB aligné EMA200(H1) ↓",
                          atr_val, price, sl, tp)

    return Signal("none",
                  f"Pas de signal (tendance {trend}, RSI={rsi_val:.1f}, "
                  f"BB [{bb_lower:.2f} ; {bb_upper:.2f}])",
                  atr_val, price, 0.0, 0.0)


def prev_rsi(row: "pd.Series") -> float:
    return float(row["rsi"])
