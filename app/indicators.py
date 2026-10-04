"""EliteBot — moteur d'indicateurs techniques (100 % numpy/pandas, sans TA-Lib)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0)


def bollinger(series: pd.Series, period: int = 20, dev: float = 2.0) -> pd.DataFrame:
    mid = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    return pd.DataFrame({"bb_upper": mid + dev * std, "bb_mid": mid, "bb_lower": mid - dev * std})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR de Wilder sur un DataFrame à colonnes high/low/close."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def add_indicators(df: pd.DataFrame, settings) -> pd.DataFrame:
    """Ajoute toutes les colonnes d'indicateurs utilisées par la stratégie."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], 20)
    out["ema200"] = ema(out["close"], settings.ema_h1_period)
    out["rsi"] = rsi(out["close"], settings.rsi_period)
    bb = bollinger(out["close"], settings.bb_period, settings.bb_dev)
    out = pd.concat([out, bb], axis=1)
    out["atr"] = atr(out, settings.atr_period)
    return out
