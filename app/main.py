"""EliteBot — serveur API FastAPI + dashboard web.

Endpoints :
  GET  /                  → dashboard (HTML)
  GET  /api/state         → snapshot complet (compte, equity, positions, logs…)
  GET  /api/health        → healthcheck (utile Render/Railway)
  POST /api/panic         → PANIC BUTTON : liquidation totale + arrêt du bot
  POST /api/bot/toggle    → active/désactive le bot
  POST /api/filters       → interrupteurs news / volatilité / horaire
  POST /api/breaker/reset → réinitialise le circuit-breaker
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import settings
from .news import news_filter
from .state import app_state
from .trader import Trader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("elitebot.api")

app = FastAPI(title="EliteBot XAUUSD", version=__version__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

trader = Trader()


@app.on_event("startup")
def _startup() -> None:
    trader.start()
    log.info("EliteBot v%s démarré — %s (port %s)", __version__, settings.symbol,
             settings.port)


@app.on_event("shutdown")
def _shutdown() -> None:
    trader.stop()


# --------------------------------------------------------------------- HTML --
@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


# -------------------------------------------------------------------- state --
@app.get("/api/state")
def api_state():
    snap = app_state.snapshot()
    snap["upcoming_news"] = news_filter.upcoming(8)
    snap["version"] = __version__
    return JSONResponse(snap)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mode": app_state.mode,
        "broker_connected": app_state.broker_connected,
        "bot_enabled": app_state.bot_enabled,
        "version": __version__,
    }


# -------------------------------------------------------------------- panic --
@app.post("/api/panic")
def api_panic():
    """Arrêt d'urgence : liquide TOUT, désactive le bot, verrouille le breaker."""
    app_state.press_panic()
    app_state.log("warning", "PANIC BUTTON pressé depuis le dashboard.")
    return {"ok": True, "message": "Liquidation immédiate déclenchée."}


# --------------------------------------------------------------------- bot ---
class ToggleBody(BaseModel):
    enabled: bool


@app.post("/api/bot/toggle")
def api_bot_toggle(body: ToggleBody):
    if body.enabled and app_state.breaker.get("tripped"):
        raise HTTPException(409, "Circuit-breaker actif jusqu'à minuit — "
                                 "réinitialisez-le d'abord (POST /api/breaker/reset).")
    app_state.set_bot_enabled(body.enabled)
    app_state.log("info", f"Bot {'ACTIVÉ' if body.enabled else 'DÉSACTIVÉ'} manuellement.")
    return {"ok": True, "bot_enabled": body.enabled}


# ------------------------------------------------------------------ filtres --
class FiltersBody(BaseModel):
    news: bool | None = None
    volatility: bool | None = None
    time: bool | None = None


@app.post("/api/filters")
def api_filters(body: FiltersBody):
    toggles = {k: v for k, v in body.model_dump().items() if v is not None}
    if not toggles:
        raise HTTPException(400, "Aucun filtre fourni (news, volatility, time).")
    app_state.set_filters(**toggles)
    app_state.log("info", f"Filtres mis à jour : {toggles}")
    return {"ok": True, "filters": app_state.get_filters()}


# ----------------------------------------------------------------- breaker ---
@app.post("/api/breaker/reset")
def api_breaker_reset():
    trader.reset_breaker()
    return {"ok": True, "breaker": app_state.breaker}


# ------------------------------------------------------------------ static ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
