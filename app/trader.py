"""EliteBot — boucle de trading : cerveau exécutif du bot.

Orchestration à chaque cycle (settings.poll_interval) :
  1. Reconnexion broker si le flux est tombé (retry avec backoff exponentiel).
  2. Panic button consommé → liquidation totale + bot désactivé.
  3. Circuit-breaker : drawdown journalier ≥ 3 % → tout liquider et bloquer
     jusqu'à minuit (UTC).
  4. Breakeven automatique : SL ramené à l'entrée après +1×ATR en gain.
  5. Analyse M5/H1 → signal → filtres (news, volatilité, horaire) → exécution.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .broker import create_broker
from .config import settings
from .news import news_filter
from .state import app_state

log = logging.getLogger("elitebot.trader")


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Trader:
    def __init__(self) -> None:
        self.broker = None
        self.mode: str = "sim"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reconnect_failures = 0
        self._cooldown_bars_left = 0
        self._last_signal_bar: str | None = None
        self._be_managed: set[int] = set()

    # ------------------------------------------------------------- lifecycle --
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_forever,
                                        name="elitebot-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ boucle main --
    def _run_forever(self) -> None:
        self.broker, self.mode = create_broker()
        app_state.mode = self.mode
        app_state.symbol = settings.symbol
        app_state.log("info",
                      f"EliteBot démarré — mode {self.mode.upper()} sur {settings.symbol}")
        consecutive_failures = 0
        while not self._stop.is_set():
            try:
                self._cycle()
                consecutive_failures = 0
            except ConnectionError as exc:
                consecutive_failures += 1
                wait = min(2 ** consecutive_failures, 60)
                app_state.broker_connected = False
                app_state.log("error",
                              f"Flux broker perdu ({exc}) — reconnexion dans {wait}s")
                log.warning("Flux broker perdu : %s — retry dans %ds", exc, wait)
                time.sleep(wait)
                try:
                    self.broker.ensure_connected()
                except Exception as exc2:                # noqa: BLE001
                    log.error("Reconnexion échouée : %s", exc2)
            except Exception as exc:                      # noqa: BLE001
                consecutive_failures += 1
                wait = min(2 ** consecutive_failures, 60)
                log.exception("Cycle interrompu : %s — retry dans %ds", exc, wait)
                time.sleep(wait)
            time.sleep(settings.poll_interval)

    # -------------------------------------------------------------- un cycle --
    def _cycle(self) -> None:
        if not self.broker.ensure_connected():
            raise ConnectionError("broker injoignable")
        app_state.broker_connected = True
        self._reconnect_failures = 0

        if self.mode == "sim":
            self.broker.advance()
        price, spread = self.broker.quote()
        app_state.set_market(price, spread)
        app_state.add_price_point(time.time(), price)

        self._sync_account()
        self._sync_positions()
        self._manage_breakeven()

        # Panic button — priorité absolue
        if app_state.consume_panic():
            self._liquidate_all("PANIC BUTTON")
            app_state.set_bot_enabled(False)
            app_state.log("warning", "PANIC BUTTON — toutes positions liquidées, "
                                     "bot désactivé.")
            return

        self._check_circuit_breaker()

        if self._cooldown_bars_left > 0:
            self._cooldown_bars_left -= 1
            app_state.set_diagnostics(cooldown_left=self._cooldown_bars_left)

        if app_state.bot_enabled and not app_state.breaker["tripped"]:
            self._maybe_trade(price, spread)

    # --------------------------------------------------------- compte/états --
    def _sync_account(self) -> None:
        acc = self.broker.account()
        equity = float(acc["equity"])
        app_state.set_account(**acc)
        app_state.add_equity_point(time.time(), equity, float(acc["balance"]))

        today = utc_today()
        daily = app_state.daily
        if daily.get("start_equity") is None or daily.get("day") != today:
            app_state.set_daily(day=today, start_equity=equity, realized=0.0,
                                pnl_day=0.0, drawdown_pct=0.0)
        else:
            start = float(daily["start_equity"])
            pnl_day = equity - start
            dd_pct = max(0.0, -pnl_day / start * 100.0) if start > 0 else 0.0
            app_state.set_daily(pnl_day=round(pnl_day, 2), drawdown_pct=round(dd_pct, 2))
            app_state.daily["day"] = today

    def _sync_positions(self) -> None:
        positions = self.broker.positions()
        app_state.set_positions(positions)
        if self.mode == "sim":
            app_state.set_account(equity=round(float(app_state.account["balance"])
                                               + sum(p["profit"] for p in positions), 2))

    def _positions_of_bot(self) -> list[dict[str, Any]]:
        return [p for p in app_state.positions if int(p.get("magic", 0)) == settings.magic]

    # ------------------------------------------------------------ liquidation --
    def _liquidate_all(self, reason: str) -> None:
        for p in list(app_state.positions):
            try:
                self.broker.close_position(p["ticket"])
                app_state.log("trade",
                              f"[{reason}] Position #{p['ticket']} fermée "
                              f"(P/L {p['profit']:.2f})")
            except Exception as exc:                      # noqa: BLE001
                log.error("Liquidation #%s impossible : %s", p["ticket"], exc)
        app_state.set_positions([])
        app_state.set_breaker(tripped=True, reason=reason,
                              tripped_at=time.time(),
                              blocked_until=self._next_midnight())

    @staticmethod
    def _next_midnight() -> float:
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow.timestamp() + 86400

    # ------------------------------------------------------- circuit-breaker --
    def _check_circuit_breaker(self) -> None:
        daily = app_state.daily
        now = time.time()
        if app_state.breaker.get("tripped"):
            until = app_state.breaker.get("blocked_until")
            if until and now >= until:
                app_state.set_breaker(tripped=False, reason=None, tripped_at=None,
                                      blocked_until=None)
                app_state.set_daily(realized=0.0)
                app_state.log("info", "Circuit-breaker réinitialisé (nouvelle journée).")
            return
        dd = float(daily.get("drawdown_pct", 0.0))
        limit = settings.max_daily_drawdown_pct
        if dd >= limit:
            self._liquidate_all(f"CIRCUIT-BREAKER {dd:.2f}% ≥ {limit}%")
            app_state.log("warning",
                          f"Circuit-breaker déclenché : drawdown {dd:.2f}% ≥ {limit}%. "
                          f"Compte bloqué jusqu'à minuit UTC.")

    # --------------------------------------------------------------- breakeven --
    def _manage_breakeven(self) -> None:
        if not settings.breakeven_enabled or self.mode != "live":
            return
        _, spread = self.broker.quote()
        for p in self._positions_of_bot():
            if p["ticket"] in self._be_managed:
                continue
            entry = float(p["open_price"])
            sl = float(p["sl"] or 0)
            atr = app_state.diagnostics.get("atr") or 0.0
            if atr <= 0:
                continue
            sign = 1.0 if p["type"] == "buy" else -1.0
            gain_atr = sign * (float(p["current_price"]) - entry) / atr
            sl_ok = (sl < entry) if sign > 0 else (sl > entry or sl == 0)
            if gain_atr >= settings.breakeven_trigger_atr and sl_ok:
                new_sl = entry + sign * settings.breakeven_lock_atr * atr
                try:
                    self.broker.modify_sl_tp(p["ticket"], new_sl, float(p["tp"]))
                    self._be_managed.add(p["ticket"])
                    app_state.log("trade", f"Breakeven #{p['ticket']} : SL → {new_sl:.2f}")
                except Exception as exc:              # noqa: BLE001
                    log.warning("Breakeven #%s échoué : %s", p["ticket"], exc)

    # ---------------------------------------------------------------- trading --
    def _maybe_trade(self, price: float, spread: float) -> None:
        from .strategy import analyze

        filters = app_state.get_filters()
        df_m5 = self.broker.rates("M5", settings.bars_m5)
        df_h1 = self.broker.rates("H1", settings.bars_h1)
        sig = analyze(df_m5, df_h1)

        checks: dict[str, Any] = {}
        checks["signal"] = sig.side
        checks["trend"] = app_state.diagnostics.get("trend", "neutral")
        checks["cooldown"] = self._cooldown_bars_left > 0
        checks["max_positions"] = len(self._positions_of_bot()) >= settings.max_open_positions
        checks["spread"] = spread > settings.max_spread
        blocked, why = news_filter.is_blocked()
        checks["news"] = blocked and filters["news"]
        hour = datetime.now(timezone.utc).hour
        checks["time"] = (filters["time"] and not
                          (settings.trading_start_hour <= hour < settings.trading_end_hour))
        vol_block = filters["volatility"] and sig.side == "none" and \
            "Volatilité insuffisante" in sig.reason
        checks["volatility"] = vol_block

        current_bar = str(df_m5.iloc[-1]["time"])
        new_bar = current_bar != self._last_signal_bar
        self._last_signal_bar = current_bar

        app_state.set_diagnostics(last_bar=current_bar, verdict=sig.reason, checks=checks)
        self._enrich_diagnostics(df_m5, df_h1)

        if sig.side == "none":
            return
        if any([checks["cooldown"], checks["max_positions"], checks["spread"],
                checks["news"], checks["time"]]):
            app_state.log("info", f"Signal {sig.side.upper()} ignoré : {checks}")
            return
        if not new_bar:
            return

        self._execute(sig, price)

    def _enrich_diagnostics(self, df_m5: "pd.DataFrame", df_h1: "pd.DataFrame") -> None:
        from .indicators import add_indicators
        df = add_indicators(df_m5.tail(120).copy(), settings)
        h1 = add_indicators(df_h1.tail(settings.ema_h1_period + 60).copy(), settings)
        last, h = df.iloc[-1], h1.iloc[-1]
        close = float(last["close"])
        ema200 = float(h["ema200"])
        trend = "neutral"
        if ema200 == ema200:
            if close > ema200 * 1.0005:
                trend = "up"
            elif close < ema200 * 0.9995:
                trend = "down"
        app_state.set_diagnostics(
            trend=trend,
            ema200_h1=round(ema200, 2) if ema200 == ema200 else None,
            rsi=round(float(last["rsi"]), 1),
            bb={"upper": round(float(last["bb_upper"]), 2),
                "mid": round(float(last["bb_mid"]), 2),
                "lower": round(float(last["bb_lower"]), 2)},
            atr=round(float(last["atr"]), 3),
            last_bar=str(df_m5.iloc[-1]["time"]),
        )

    # ------------------------------------------------------------- exécution --
    def _execute(self, sig, price: float) -> None:
        acc = self.broker.account()
        equity = float(acc["equity"])
        spec = self.broker.symbol_spec()
        lots = self._position_size(equity, sig.sl, sig.entry, spec)
        if lots <= 0:
            app_state.log("warning", "Taille de lot calculée nulle — trade annulé.")
            return
        try:
            res = self.broker.open_position(sig.side, lots, sig.sl, sig.tp)
            self._cooldown_bars_left = settings.cooldown_bars
            app_state.update_stats(trades_today=app_state.stats["trades_today"] + 1)
            app_state.log("trade",
                          f"{sig.side.upper()} {lots} lot(s) @ {res['price']:.2f} | "
                          f"SL {sig.sl:.2f} TP {sig.tp:.2f} | {sig.reason}")
        except Exception as exc:                          # noqa: BLE001
            log.exception("Exécution échouée : %s", exc)
            app_state.log("error", f"Exécution échouée : {exc}")

    @staticmethod
    def _position_size(equity: float, sl: float, entry: float, spec: dict[str, Any]) -> float:
        """Risque strict : 1 % de l'équité par transaction (distance SL en $)."""
        risk_amount = equity * settings.risk_percent / 100.0
        stop_distance = abs(entry - sl)
        if stop_distance <= 0:
            return 0.0
        contract = float(spec["contract"])
        value_per_lot_per_unit = contract                # 1 lot = 100 oz → 100 $ / $ de prix
        raw = risk_amount / (stop_distance * value_per_lot_per_unit)
        step = float(spec["volume_step"])
        lots = math_floor_step(raw, step)
        return max(0.0, min(lots, settings.max_lots))

    # ------------------------------------------------------------ API externe --
    def panic(self) -> dict[str, Any]:
        app_state.press_panic()
        return {"panic": True}

    def liquidate_now(self) -> int:
        n = 0
        for p in list(app_state.positions):
            try:
                self.broker.close_position(p["ticket"])
                n += 1
            except Exception:                             # noqa: BLE001
                pass
        return n

    def reset_breaker(self) -> None:
        app_state.set_breaker(tripped=False, reason=None, tripped_at=None,
                              blocked_until=None)
        app_state.set_daily(realized=0.0)
        app_state.log("info", "Circuit-breaker réinitialisé manuellement.")


def math_floor_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step
