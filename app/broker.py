"""EliteBot — couche broker unifiée.

Deux implémentations :
  • MT5Broker  : pont natif vers le terminal MetaTrader 5 (Windows / VPS),
                 avec reconnexion automatique en boucle infinie.
  • SimBroker  : moteur de paper-trading déterministe pour le déploiement
                 cloud (Render / Railway / Replit), où MetaTrader5 n'existe pas.

La sélection est automatique via settings.mode : "live", "sim" ou "auto".
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .config import settings
from .sim_clock import MarketClock

log = logging.getLogger("elitebot.broker")


# --------------------------------------------------------------------------- #
#  Pont MetaTrader 5 natif
# --------------------------------------------------------------------------- #
class MT5Broker:
    """Exécution réelle via le terminal MetaTrader 5."""

    def __init__(self) -> None:
        import MetaTrader5 as mt5  # import local : indisponible sous Linux

        self.mt5 = mt5
        self.connected = False

    # ------------------------------------------------------------ connexion --
    def connect(self) -> bool:
        mt5 = self.mt5
        kwargs: dict[str, Any] = {}
        if settings.mt5_terminal_path:
            kwargs["path"] = settings.mt5_terminal_path
        if not mt5.initialize(**kwargs):
            log.error("MT5 initialize failed: %s", mt5.last_error())
            return False
        if settings.mt5_login:
            if not mt5.login(settings.mt5_login, password=settings.mt5_password,
                             server=settings.mt5_server):
                log.error("MT5 login failed: %s", mt5.last_error())
                mt5.shutdown()
                return False
        mt5.symbol_select(settings.symbol, True)
        self.connected = True
        return True

    def disconnect(self) -> None:
        try:
            self.mt5.shutdown()
        finally:
            self.connected = False

    def ensure_connected(self) -> bool:
        """Reconnexion automatique : vérifie le flux, relance initialize/login."""
        if self.connected and self.mt5.terminal_info() is not None:
            info = self.mt5.account_info()
            if info is not None:
                return True
        log.warning("Flux broker interrompu — reconnexion MT5…")
        self.disconnect()
        for attempt in range(1, 4):
            if self.connect():
                log.info("Reconnexion MT5 réussie (tentative %d)", attempt)
                return True
            time.sleep(min(2 ** attempt, 30))
        return False

    # -------------------------------------------------------------- marché ---
    def quote(self) -> tuple[float, float]:
        t = self.mt5.symbol_info_tick(settings.symbol)
        if t is None or t.bid <= 0 or t.ask <= 0:
            raise ConnectionError("tick indisponible")
        return float(t.bid), float(t.ask - t.bid)

    def rates(self, timeframe: int, count: int) -> pd.DataFrame:
        raw = self.mt5.copy_rates_from_pos(settings.symbol, timeframe, 0, count)
        if raw is None or len(raw) == 0:
            raise ConnectionError("copy_rates_from_pos a échoué")
        df = pd.DataFrame(raw)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df[["time", "open", "high", "low", "close"]]

    # -------------------------------------------------------------- compte ---
    def account(self) -> dict[str, Any]:
        a = self.mt5.account_info()
        if a is None:
            raise ConnectionError("account_info indisponible")
        return {
            "login": str(a.login), "server": a.server, "currency": a.currency,
            "balance": a.balance, "equity": a.equity, "floating": a.profit,
            "margin_free": a.margin_free, "leverage": a.leverage,
        }

    def positions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in (self.mt5.positions_get(symbol=settings.symbol) or []):
            out.append({
                "ticket": p.ticket, "type": "buy" if p.type == 0 else "sell",
                "volume": p.volume, "open_price": p.price_open, "current_price": p.price_current,
                "sl": p.sl, "tp": p.tp, "profit": p.profit, "time": p.time,
                "comment": p.comment, "magic": p.magic,
            })
        return out

    # ------------------------------------------------------- spécifications --
    def symbol_spec(self) -> dict[str, Any]:
        info = self.mt5.symbol_info(settings.symbol)
        if info is None:
            raise ConnectionError("symbol_info indisponible")
        contract = info.trade_contract_size or 100.0
        return {
            "digits": info.digits,
            "point": info.point,
            "contract": contract,
            "volume_min": info.volume_min,
            "volume_step": info.volume_step or 0.01,
            "volume_max": info.volume_max,
            "stops_level": getattr(info, "trade_stops_level", 0) * info.point,
        }

    # ------------------------------------------------------------ exécution --
    def _fill_mode(self) -> int:
        mt5 = self.mt5
        return mt5.ORDER_FILLING_IOC

    def open_position(self, side: str, lots: float, sl: float, tp: float,
                      comment: str = "EliteBot") -> dict[str, Any]:
        mt5 = self.mt5
        tick = self.mt5.symbol_info_tick(settings.symbol)
        price = tick.ask if side == "buy" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": settings.symbol,
            "volume": float(lots),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": settings.magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._fill_mode(),
        }
        res = mt5.order_send(req)
        if res is None:
            raise ConnectionError(f"order_send sans réponse : {mt5.last_error()}")
        if res.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
            raise RuntimeError(f"order_send refusé: retcode={res.retcode} {res.comment}")
        return {"ticket": res.order, "price": res.price or price, "lots": lots,
                "side": side, "sl": sl, "tp": tp}

    def close_position(self, ticket: int) -> None:
        positions = self.mt5.positions_get(ticket=ticket) or []
        if not positions:
            return
        p = positions[0]
        tick = self.mt5.symbol_info_tick(settings.symbol)
        is_buy = p.type == 0
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": settings.symbol,
            "volume": p.volume,
            "type": self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": settings.magic,
            "comment": "EliteBot close",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._fill_mode(),
        }
        res = self.mt5.order_send(req)
        if res is None or res.retcode not in (
            self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_DONE_PARTIAL
        ):
            raise RuntimeError(f"close refusé pour #{ticket}: "
                               f"{res.retcode if res else self.mt5.last_error()}")

    def modify_sl_tp(self, ticket: int, sl: float, tp: float) -> None:
        req = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "symbol": settings.symbol,
            "position": ticket,
            "sl": float(sl),
            "tp": float(tp),
        }
        self.mt5.order_send(req)


# --------------------------------------------------------------------------- #
#  Broker de simulation (paper trading cloud)
# --------------------------------------------------------------------------- #
class SimBroker:
    """Réplique fidèle du comportement MT5 sans terminal : fill au prix du marché,
    P/L latent recalculé à chaque tick, SL/TP exécutés automatiquement."""

    def __init__(self) -> None:
        self.clock = MarketClock()
        self.connected = True
        self._lock = threading.Lock()
        self._positions: dict[int, dict[str, Any]] = []
        self._ticket = 90_000_000
        self.balance = settings.sim_balance
        self.currency = "USD"
        self.leverage = 100
        self._contract = 100.0          # 1 lot XAUUSD = 100 oz
        self._realized_day: float = 0.0
        self._day_key: str = ""

    # ------------------------------------------------------------ connexion --
    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def ensure_connected(self) -> bool:
        return True

    # -------------------------------------------------------------- marché ---
    def quote(self) -> tuple[float, float]:
        price, spread = self.clock.quote()
        return price, spread

    def rates(self, timeframe: str, count: int) -> pd.DataFrame:
        if timeframe == "M5":
            return self.clock.get_m5(count)
        return self.clock.get_h1(count)

    def tick_clock(self) -> None:
        self.clock.tick()

    # -------------------------------------------------------------- compte ---
    def account(self) -> dict[str, Any]:
        floating = sum(p["profit"] for p in self._positions)
        return {
            "login": "SIM-DEMO", "server": "EliteBot-Paper", "currency": self.currency,
            "balance": round(self.balance, 2), "equity": round(self.balance + floating, 2),
            "floating": round(floating, 2), "margin_free": round(self.balance, 2),
            "leverage": self.leverage,
        }

    def positions(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._positions]

    # ------------------------------------------------------- spécifications --
    def symbol_spec(self) -> dict[str, Any]:
        return {"digits": 2, "point": 0.01, "contract": self._contract,
                "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0,
                "stops_level": 0.0}

    # ------------------------------------------------------------ exécution --
    def open_position(self, side: str, lots: float, sl: float, tp: float,
                      comment: str = "EliteBot") -> dict[str, Any]:
        price, _ = self.quote()
        price = price + (0.03 if side == "buy" else -0.03)  # léger slippage réaliste
        self._ticket += 1
        pos = {
            "ticket": self._ticket, "type": side, "volume": lots,
            "open_price": round(price, 2), "current_price": price,
            "sl": round(sl, 2), "tp": round(tp, 2),
            "profit": 0.0, "time": int(time.time()), "comment": comment,
            "magic": settings.magic,
        }
        self._positions.append(pos)
        return {"ticket": pos["ticket"], "price": pos["open_price"], "lots": lots,
                "side": side, "sl": sl, "tp": tp}

    def close_position(self, ticket: int) -> None:
        pos = next((p for p in self._positions if p["ticket"] == ticket), None)
        if pos is None:
            return
        price, _ = self.quote()
        sign = 1.0 if pos["type"] == "buy" else -1.0
        pnl = sign * (price - pos["open_price"]) * pos["volume"] * self._contract
        pnl -= pos["volume"] * self._contract * 0.00003 * price  # commission ~0.3pip
        self.balance += pnl
        self._positions.remove(pos)

    def modify_sl_tp(self, ticket: int, sl: float, tp: float) -> None:
        for p in self._positions:
            if p["ticket"] == ticket:
                p["sl"] = round(sl, 2)
                p["tp"] = round(tp, 2)

    # ------------------------------------------------------ moteur de marché --
    def advance(self) -> None:
        """Fait vivre le marché simulé : nouvelle bougie, P/L, SL/TP."""
        self.tick_clock()
        price, spread = self.quote()
        with self._lock:
            closed: list[tuple[dict, float, str]] = []
            for p in self._positions:
                sign = 1.0 if p["type"] == "buy" else -1.0
                p["current_price"] = price
                p["profit"] = round(sign * (price - p["open_price"]) * p["volume"]
                                    * self._contract, 2)
                hit_sl = (p["type"] == "buy" and price <= p["sl"]) or \
                         (p["type"] == "sell" and price >= p["sl"])
                hit_tp = (p["type"] == "buy" and price >= p["tp"]) or \
                         (p["type"] == "sell" and price <= p["tp"])
                if hit_sl:
                    closed.append((p, p["sl"], "SL"))
                elif hit_tp:
                    closed.append((p, p["tp"], "TP"))
            for p, exit_price, reason in closed:
                sign = 1.0 if p["type"] == "buy" else -1.0
                pnl = sign * (exit_price - p["open_price"]) * p["volume"] * self._contract
                self.balance += pnl
                self._positions.remove(p)
                p["exit_reason"] = reason
                p["pnl"] = round(pnl, 2)


# --------------------------------------------------------------------------- #
#  Fabrique
# --------------------------------------------------------------------------- #
def create_broker() -> tuple[Any, str]:
    """Choisit le backend selon MODE et la disponibilité de MetaTrader5."""
    mode = settings.mode.lower()
    if mode in ("sim", "paper"):
        return SimBroker(), "sim"
    if mode == "live":
        broker = MT5Broker()
        if not broker.connect():
            raise RuntimeError("MODE=live mais connexion MetaTrader 5 impossible — "
                               "vérifiez MT5_LOGIN / MT5_PASSWORD / MT5_SERVER.")
        return broker, "live"
    # auto : tente MT5, sinon simulation
    try:
        import MetaTrader5  # noqa: F401
        broker = MT5Broker()
        if broker.connect():
            return broker, "live"
        log.warning("MT5 présent mais connexion refusée → bascule en simulation.")
    except ImportError:
        log.warning("MetaTrader5 indisponible sur cet hôte → mode simulation.")
    return SimBroker(), "sim"
