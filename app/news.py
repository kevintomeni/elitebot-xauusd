"""EliteBot — filtre de news macroéconomique.

Source : calendrier ForexFactory (JSON hebdomadaire, gratuit). Le filtre bloque
toute nouvelle ouverture ±30 min autour des événements majeurs (USD/EUR par
défaut). En cas d'échec du flux, comportement configurable (fail-open par
défaut, fail-closed possible via NEWS_FAIL_CLOSED=true).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .config import settings
from .state import app_state

log = logging.getLogger("elitebot.news")

IMPACT_ORDER = {"High": 3, "Medium": 2, "Low": 1, "Non-Economic": 0}


class NewsFilter:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._last_fetch: float = 0.0
        self._lock = threading.Lock()

    # --------------------------------------------------------- récupération --
    def _fetch(self) -> list[dict[str, Any]]:
        resp = requests.get(settings.news_calendar_url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EliteBot/1.0)"
        })
        resp.raise_for_status()
        raw = resp.json()
        wanted = settings.news_currency_set
        min_impact = IMPACT_ORDER.get(settings.news_impact.capitalize(), 3)
        events: list[dict[str, Any]] = []
        for item in raw:
            try:
                dt = self._parse_date(item.get("date", ""))
            except (ValueError, TypeError):
                continue
            impact = (item.get("impact") or "").capitalize()
            currency = (item.get("country") or item.get("currency") or "").upper()
            if currency not in wanted or IMPACT_ORDER.get(impact, 0) < min_impact:
                continue
            events.append({"time": dt.timestamp(), "title": item.get("title", ""),
                           "currency": currency, "impact": impact})
        return events

    @staticmethod
    def _parse_date(raw: str) -> datetime:
        # Format ForexFactory : "2026-10-05T08:30:00-04:00"
        return datetime.fromisoformat(raw)

    def refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_fetch < 6 * 3600:
            return
        try:
            events = self._fetch()
            with self._lock:
                self._events = events
            app_state.news = sorted(events, key=lambda e: e["time"])[:12]
            app_state.news_status = (
                f"{len(events)} événements {settings.news_impact} chargés "
                f"({', '.join(sorted(settings.news_currency_set))})"
            )
            self._last_fetch = now
        except Exception as exc:                       # noqa: BLE001
            log.warning("Calendrier indisponible : %s", exc)
            app_state.news_status = f"Calendrier KO ({exc.__class__.__name__}) — "
            app_state.news_status += "mode fail-closed" if settings.news_fail_closed \
                else "trading autorisé (fail-open)"
            if settings.news_fail_closed:
                with self._lock:
                    self._events = [{"time": now, "title": "CALENDRIER INDISPONIBLE — "
                                     "blocage fail-closed", "currency": "***",
                                     "impact": "High"}]

    # ------------------------------------------------------------- décision --
    def is_blocked(self, now: float | None = None) -> tuple[bool, str]:
        now = now or time.time()
        if not app_state.get_filters().get("news", True):
            return False, "Filtre de news désactivé"
        self.refresh()
        with self._lock:
            events = list(self._events)
        if not events:
            if settings.news_fail_closed:
                return True, "News: calendrier indisponible (fail-closed)"
            return False, "News: aucun événement chargé"
        before = settings.news_block_before_min * 60
        after = settings.news_block_after_min * 60
        for ev in events:
            delta = ev["time"] - now
            if -after <= delta <= before:
                if delta >= 0:
                    return True, (f"News: {ev['currency']} « {ev['title']} » dans "
                                  f"{int(delta // 60)} min")
                return True, (f"News: {ev['currency']} « {ev['title']} » il y a "
                              f"{int(-delta // 60)} min")
        nxt = [e for e in events if e["time"] > now]
        if nxt:
            mins = int((nxt[0]["time"] - now) // 60)
            return False, f"News: OK (prochain event dans {mins} min)"
        return False, "News: OK"

    def upcoming(self, count: int = 8) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            events = sorted(self._events, key=lambda e: e["time"])
        return [e for e in events if e["time"] >= now][:count]


news_filter = NewsFilter()
