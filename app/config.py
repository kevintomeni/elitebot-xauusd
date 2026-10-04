"""EliteBot — configuration centralisée lue depuis les variables d'environnement.

Tous les identifiants sensibles (compte MT5, mot de passe, serveur) proviennent
uniquement des env vars : jamais de secret dans le code ou le dépôt Git.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _load_config_file() -> dict:
    """Charge les valeurs par défaut du fichier config.json (sans secrets)."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _env_str(name: str, default: str) -> str:
    # L'environnement a priorité sur config.json, config.json a priorité sur default
    value = os.getenv(name)
    if value is not None and value.strip() != "":
        return value.strip()
    return str(_load_config_file().get(name, default))
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(_env_str(name, str(default))))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name, "1" if default else "0").lower()
    return raw in ("1", "true", "yes", "on", "y")


@dataclass
class Settings:
    # ------------------------------------------------------------------ MT5 --
    # Identifiants du terminal MetaTrader 5 (LIVE/DEMO). Sur un hébergeur
    # Linux (Render/Railway/Replit), MetaTrader5 n'est pas disponible et le
    # bot bascule automatiquement en mode SIMULATION (paper trading).
    mt5_login: int = _env_int("MT5_LOGIN", 0)
    mt5_password: str = _env_str("MT5_PASSWORD", "")
    mt5_server: str = _env_str("MT5_SERVER", "")
    mt5_terminal_path: str = _env_str("MT5_TERMINAL_PATH", "")

    # ------------------------------------------------------------- Trading --
    symbol: str = _env_str("SYMBOL", "XAUUSD")
    mode: str = _env_str("MODE", "auto")          # auto | live | sim
    magic: int = _env_int("MAGIC", 860402)
    risk_percent: float = _env_float("RISK_PERCENT", 1.0)      # % équité / trade
    max_daily_drawdown_pct: float = _env_float("MAX_DAILY_DRAWDOWN_PCT", 3.0)

    # --------------------------------------------------------- Indicateurs --
    rsi_period: int = _env_int("RSI_PERIOD", 14)
    bb_period: int = _env_int("BB_PERIOD", 20)
    bb_dev: float = _env_float("BB_DEV", 2.0)
    ema_h1_period: int = _env_int("EMA_H1_PERIOD", 200)
    atr_period: int = _env_int("ATR_PERIOD", 14)

    # ---------------------------------------------------- Gestion du risque --
    sl_atr_mult: float = _env_float("SL_ATR_MULT", 1.5)
    tp_atr_mult: float = _env_float("TP_ATR_MULT", 3.0)
    max_lots: float = _env_float("MAX_LOTS", 10.0)
    max_open_positions: int = _env_int("MAX_OPEN_POSITIONS", 1)
    cooldown_bars: int = _env_int("COOLDOWN_BARS", 2)
    breakeven_enabled: bool = _env_bool("BREAKEVEN_ENABLED", True)
    breakeven_trigger_atr: float = _env_float("BREAKEVEN_TRIGGER_ATR", 1.0)
    breakeven_lock_atr: float = _env_float("BREAKEVEN_LOCK_ATR", 0.2)

    # --------------------------------------------------- Filtre volatilité --
    min_atr: float = _env_float("MIN_ATR", 0.10)         # seuil absolu (prix)
    min_atr_ratio: float = _env_float("MIN_ATR_RATIO", 0.0002)  # ATR / prix
    max_spread: float = _env_float("MAX_SPREAD", 0.50)   # spread max (points prix)

    # ------------------------------------------------------- Filtre horaire --
    time_filter_enabled: bool = _env_bool("TIME_FILTER_ENABLED", True)
    trading_start_hour: int = _env_int("TRADING_START_HOUR", 7)   # UTC
    trading_end_hour: int = _env_int("TRADING_END_HOUR", 21)      # UTC

    # -------------------------------------------------------- Filtre news ---
    news_filter_enabled: bool = _env_bool("NEWS_FILTER_ENABLED", True)
    news_impact: str = _env_str("NEWS_IMPACT", "High")            # High | Medium
    news_currencies: str = _env_str("NEWS_CURRENCIES", "USD,EUR")
    news_block_before_min: int = _env_int("NEWS_BLOCK_BEFORE_MIN", 30)
    news_block_after_min: int = _env_int("NEWS_BLOCK_AFTER_MIN", 30)
    news_fail_closed: bool = _env_bool("NEWS_FAIL_CLOSED", False)  # True = bloquer si flux KO
    news_calendar_url: str = _env_str(
        "NEWS_CALENDAR_URL",
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    )

    # ------------------------------------------------------------ Divers ----
    poll_interval: float = _env_float("POLL_INTERVAL", 1.0)       # s, cycle moteur
    bars_m5: int = _env_int("BARS_M5", 600)
    bars_h1: int = _env_int("BARS_H1", 420)
    sim_balance: float = _env_float("SIM_BALANCE", 10000.0)
    sim_base_price: float = _env_float("SIM_BASE_PRICE", 2650.0)
    sim_speed: float = _env_float("SIM_SPEED", 1.0)               # 60 = démo accélérée
    dashboard_password: str = _env_str("DASHBOARD_PASSWORD", "")
    port: int = _env_int("PORT", 8000)

    @property
    def news_currency_set(self) -> set[str]:
        return {c.strip().upper() for c in self.news_currencies.split(",") if c.strip()}


# ── Configuration finale : config.json < variables d'environnement < valeurs par défaut
settings = Settings()


settings = Settings()
