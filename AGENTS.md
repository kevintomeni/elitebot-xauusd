# EliteBot XAUUSD — Guide d'utilisation

## Structure du projet

```
elitebot/
├── app/                      # Serveur FastAPI + moteur de trading
│   ├── main.py               # API FastAPI + dashboard HTML statique
│   ├── trader.py             # Boucle de trading (circuit-breaker, panic, breakeven)
│   ├── strategy.py           # Stratégie hybride M5/H1 (RSI + BB + EMA200)
│   ├── indicators.py         # RSI, Bollinger, EMA, ATR (numpy/pandas)
│   ├── broker.py             # Pont MT5 natif (reconnexion infinie) + SimBroker (cloud)
│   ├── sim_clock.py          # Générateur de marché M5/H1 réaliste (simulation)
│   ├── news.py               # Filtre de news macro (±30 min via ForexFactory)
│   ├── state.py              # État partagé thread-safe
│   ├── config.py             # Configuration : env vars > config.json > défauts
│   ├── static/               # Dashboard : index.html, style.css, app.js
├── config.json               # Configuration (sans secrets)
├── config.example.json       # Exemple de config.json
├── .env.example              # Modèle des variables d'environnement
├── requirements.txt          # Dépendances (versions épinglées)
├── Dockerfile                # Image Docker optimisée
├── render.yaml               # Blueprint Render (déploiement un clic)
├── Procfile                  # Démarrage pour Replit/hebos sans Docker
├── start-elitebot.bat        # Lancement Windows (installation automatique + bot)
├── start-elitebot.sh         # Lancement macOS/Linux (même principe)
└── README.md                 # Documentation complète
```

## Démarrage rapide

### Windows
```bat
start-elitebot.bat
```

### macOS / Linux
```bash
chmod +x start-elitebot.sh
./start-elitebot.sh
```

### Docker
```bash
docker build -t elitebot .
docker run -p 8000:8000 --env-file .env elitebot
```

## Configuration

L'ordre de priorité : **variables d'environnement > config.json > valeurs par défaut**.

- `MODE=auto` : tente MT5 si le terminal est démarré, sinon simulation (recommandé)
- `MODE=live` : connexion réelle (exige MT5 installé + identifiants + terminal ouvert)
- `MODE=sim` : simulation uniquement (démo, sans risque de perte)

Identifiants réels : `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_TERMINAL_PATH`.

## Points de contrôle essentiels

- `GET /api/health` — healthcheck (Render/Railway/Replit)
- `GET /api/state` — snapshot complet du trading (compte, equity, positions, logs, diagnostic)
- `POST /api/panic` — **PANIC BUTTON** : liquidation totale + désactivation du robot
- `POST /api/bot/toggle` — `{"enabled": true|false}`
- `POST /api/filters` — `{"news": bool, "volatility": bool, "time": bool}`
- `POST /api/breaker/reset` — réinitialisation du circuit-breaker

## Sécurité

- Aucun secret dans le code ou le dépôt (`.gitignore` exclut `.env` et `config.json` si sensible)
- Le circuit-breaker bloque jusqu'à minuit UTC si drawdown ≥ 3 %
- Le Dashboard est protégé si `DASHBOARD_PASSWORD` est défini

## Tests de validation

```bash
python -m compileall -q app
python -c "from app.strategy import analyze; from app.sim_clock import MarketClock; from app.config import settings; analyze(MarketClock().get_m5(settings.bars_m5), MarketClock().get_h1(settings.bars_h1))"
```

## Déploiement sur un hébergeur gratuit

- **Render** : `render.yaml` (plan free) — service web avec healthcheck `/api/health`
- **Railway** : `Dockerfile` (point d'entrée par défaut)
- **Replit** : `Procfile` (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`)
- **Hugging Face Spaces** : compatible (FastAPI + static, serving sur le port 8000)

Le port utilisé est lu depuis `$PORT` (injecté par tous les hébergeurs), valeur par défaut 8000.
