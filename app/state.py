"""État partagé thread-safe entre le moteur de trading, le filtre de news et l'API."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class AppState:
    """Mémoire centrale de l'application, protégée par un verrou."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.started_at = time.time()

        # Interrupteurs pilotables depuis le dashboard
        self.bot_enabled: bool = True
        self.panic_pressed: bool = False
        self.filters: dict[str, bool] = {"news": True, "volatility": True, "time": True}

        # Brokers / connexion
        self.mode: str = "sim"                 # sim | live
        self.broker_connected: bool = False
        self.symbol: str = "XAUUSD"

        # Compte
        self.account: dict[str, Any] = {
            "login": "—", "server": "—", "currency": "USD",
            "balance": 0.0, "equity": 0.0, "floating": 0.0,
            "margin_free": 0.0, "leverage": 0,
        }

        # Marché
        self.price: float = 0.0
        self.spread: float = 0.0
        self.price_history: deque[tuple[float, float]] = deque(maxlen=1200)  # (ts, close)

        # Performance
        self.equity_curve: deque[tuple[float, float, float]] = deque(maxlen=20000)  # ts, equity, balance
        self.trade_log: deque[dict[str, Any]] = deque(maxlen=300)

        # Positions & stats
        self.positions: list[dict[str, Any]] = []
        self.stats: dict[str, int] = {"trades_today": 0, "wins": 0, "losses": 0, "open_count": 0}
        self.daily: dict[str, Any] = {"realized": 0.0, "pnl_day": 0.0, "start_equity": 0.0,
                                      "drawdown_pct": 0.0}

        # Diagnostic moteur
        self.diagnostics: dict[str, Any] = {
            "trend": "neutral", "ema200_h1": None, "rsi": None, "atr": None,
            "bb": {"upper": None, "mid": None, "lower": None},
            "last_bar": None, "verdict": "Initialisation…", "cooldown_left": 0,
            "checks": {}, "last_signal_bar": None,
        }

        # Circuit breaker
        self.breaker: dict[str, Any] = {
            "tripped": False, "tripped_at": None, "blocked_until": None, "reason": None,
        }

        # News
        self.news: list[dict[str, Any]] = []
        self.news_status: str = "Chargement du calendrier…"

        self.last_update: float = 0.0

    # ---------------------------------------------------------------- utils --
    def log(self, kind: str, message: str, **extra: Any) -> None:
        entry = {"ts": time.time(), "kind": kind, "message": message}
        entry.update(extra)
        with self._lock:
            self.trade_log.appendleft(entry)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            curve = list(self.equity_curve)
            prices = list(self.price_history)
            return {
                "mode": self.mode,
                "broker_connected": self.broker_connected,
                "bot_enabled": self.bot_enabled,
                "panic_pressed": self.panic_pressed,
                "symbol": self.symbol,
                "account": dict(self.account),
                "daily": dict(self.daily),
                "stats": dict(self.stats),
                "positions": [dict(p) for p in self.positions],
                "equity_curve": curve[-1440:],
                "price_history": prices[-400:],
                "trade_log": list(self.trade_log)[:120],
                "diagnostics": self.diagnostics,
                "breaker": dict(self.breaker),
                "filters": dict(self.filters),
                "news": list(self.news)[:12],
                "news_status": self.news_status,
                "price": self.price,
                "spread": self.spread,
                "server_time": time.time(),
                "started_at": self.started_at,
                "last_update": self.last_update,
            }

    # --------------------------------------------------------------- setters --
    def set_account(self, **fields: Any) -> None:
        with self._lock:
            self.account.update(fields)
            self.last_update = time.time()

    def set_market(self, price: float, spread: float) -> None:
        with self._lock:
            self.price = price
            self.spread = spread

    def set_positions(self, positions: list[dict[str, Any]]) -> None:
        with self._lock:
            self.positions = positions
            self.stats["open_count"] = len(positions)

    def set_diagnostics(self, **fields: Any) -> None:
        with self._lock:
            self.diagnostics.update(fields)

    def set_breaker(self, **fields: Any) -> None:
        with self._lock:
            self.breaker.update(fields)

    def set_filters(self, **toggles: bool) -> None:
        with self._lock:
            for key, value in toggles.items():
                if key in self.filters:
                    self.filters[key] = bool(value)

    def get_filters(self) -> dict[str, bool]:
        with self._lock:
            return dict(self.filters)

    def set_bot_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.bot_enabled = bool(enabled)

    def press_panic(self) -> None:
        with self._lock:
            self.panic_pressed = True

    def consume_panic(self) -> bool:
        with self._lock:
            if self.panic_pressed:
                self.panic_pressed = False
                return True
            return False

    def add_equity_point(self, ts: float, equity: float, balance: float) -> None:
        with self._lock:
            self.equity_curve.append((ts, round(equity, 2), round(balance, 2)))

    def add_price_point(self, ts: float, close: float) -> None:
        with self._lock:
            self.price_history.append((ts, round(close, 2)))

    def update_stats(self, **fields: int) -> None:
        with self._lock:
            self.stats.update(fields)

    def set_daily(self, **fields: Any) -> None:
        with self._lock:
            self.daily.update(fields)


app_state = AppState()
