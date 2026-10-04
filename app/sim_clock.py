"""EliteBot — horloge de marché pour le mode simulation (paper trading).

Sur un hébergeur Linux (Render, Railway, Replit, Hugging Face), la bibliothèque
MetaTrader5 n'est pas disponible : le bot bascule alors automatiquement en mode
SIMULATION. Cette horloge fabrique des bougies M5/H1 réalistes (marché 24/5,
plusieurs mois d'historique) afin de valider toute la chaîne quant.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import settings


class MarketClock:
    """Générateur de bougies M5 synthétiques cohérentes, marché 24/5."""

    def __init__(self) -> None:
        self.base_price = settings.sim_base_price
        self.price = self.base_price
        self.step = 0
        self._rng = random.Random(20260402)
        self._m5_ts = self._align_m5(time.time()) - 5 * 60
        self._open = self.price
        self._h, self._l = self.price, self.price
        self._c = self.price
        self._drift = 0.0
        self._cur_h1_ts = self._h1_of(self._m5_ts)
        self._h1_hist: list[float] = []
        self._seed_history()

    # ------------------------------------------------------------- helpers --
    @staticmethod
    def _align_m5(ts: float) -> float:
        return math.floor(ts / 300.0) * 300.0

    @staticmethod
    def _h1_of(ts: float) -> float:
        return math.floor(ts / 3600.0) * 3600.0

    def _market_open(self, ts: float) -> bool:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.weekday() < 5  # lundi(0) → vendredi(4), 24h

    def _drift_for(self, ts: float) -> float:
        hour = int((ts % 86400) // 3600)          # heure UTC, sans datetime
        if 7 <= hour < 17:      # session Londres + NY : tendance franche
            return self._rng.choice([-1.0, 1.0]) * 0.9
        if 17 <= hour < 21:     # fin de session : plus calme
            return self._rng.choice([-1.0, 1.0]) * 0.35
        return self._rng.choice([-1.0, 1.0]) * 0.15

    def _tick_price(self, ts: float) -> None:
        self._drift += self._rng.gauss(0.0, 0.02)
        self._drift = max(-0.25, min(0.25, self._drift)) * 0.97 + self._drift_for(ts) * 0.02
        vol = 0.085
        self.price += self._rng.gauss(0.0, vol) + self._drift
        self.price = max(1200.0, min(4500.0, self.price))

    def _build_m5_candle(self, ts: float) -> dict:
        o = self._open
        h = o
        l = o
        for _ in range(24):                       # 24 ticks intra-bougie de 5 min
            self._tick_price(ts)
            h = max(h, self.price)
            l = min(l, self.price)
        c = self.price
        self._open = c              # continuité : l'open suivant = ce close
        return {"ts": ts, "open": o, "high": h, "low": l, "close": c}

    def _seed_history(self) -> None:
        """Rejoue ~90 jours de marché (26 000 bougies M5) au chargement."""
        start = self._m5_ts - 90 * 24 * 12 * 300
        hist: list[dict] = []
        ts = start
        while ts <= self._m5_ts:
            if self._market_open(ts):
                cand = self._build_m5_candle(ts)
                hist.append(cand)
                h1 = self._h1_of(ts)
                if hist and h1 != self._cur_h1_ts:
                    self._cur_h1_ts = h1
            ts += 300
        self._history = hist

    # -------------------------------------------------------------- output --
    def get_m5(self, bars: int | None = None) -> pd.DataFrame:
        n = bars or settings.bars_m5
        rows = self._history[-n:]
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True)
        return df[["time", "open", "high", "low", "close"]]

    def get_h1(self, bars: int | None = None) -> pd.DataFrame:
        n = bars or settings.bars_h1
        df = self.get_m5(90 * 24 * 12)
        df = df.set_index("time")
        h1 = df["close"].resample("1h").ohlc().dropna()
        h1 = h1.reset_index()
        return h1.tail(n)[["time", "open", "high", "low", "close"]]

    def tick(self) -> None:
        """Avance d'une bougie M5 : appelé par la boucle du bot."""
        now = self._align_m5(time.time())
        if now <= self._m5_ts:
            return
        while self._m5_ts < now:
            self._m5_ts += 300
            if self._market_open(self._m5_ts):
                self._history.append(self._build_m5_candle(self._m5_ts))
        self._open = self.price
        self._h = self._l = self.price

    def quote(self) -> tuple[float, float]:
        """Prix courant + spread simulé (0.25 $ en moyenne sur l'or)."""
        jitter = self._rng.gauss(0.0, 0.05)
        return round(self.price + jitter, 2), 0.25
