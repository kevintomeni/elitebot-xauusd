# EliteBot XAUUSD — Trading quant automatisé (réplique du bot Elite)

Bot de trading algorithmique sur l'or (XAUUSD), côté API Python (FastAPI) avec intégration MetaTrader5, stratégie quant M5/H1, gestion du risque institutionnelle, circuit-breaker anti-ruine, filtre de news. Dashboard web temps réel avec **Panic Button**.

> ⚠️ **Avertissement** : le trading sur marge comporte un risque de perte en capital.
> Testez toujours sur un compte démo avant tout usage réel.

---

## 1. Démarrage — le plus simple possible

### Windows
```bat
start-elitebot.bat
```
2 clics : le script vérifie Python/pip, installe les dépendances, génère `config.json`, demande les identifiants, et lance le serveur sur `http://localhost:8000`.

### macOS / Linux
```bash
chmod +x start-elitebot.sh && ./start-elitebot.sh
```

### Docker (tout OS)
```bash
docker build -t elitebot .
docker run -p 8000:8000 --env-file .env elitebot
```

Le port est lu depuis `$PORT` (injecté par tous les hébergeurs, valeur par défaut 8000).

---

## 2. Configuration (3 niveaux, priorité croissante)

L'ordre de priorité est : **variables d'environnement > config.json > valeurs par défaut**.

### A. variables d'environnement (sécurisées — jamais dans le code)
`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_TERMINAL_PATH`, `MODE`, `RISK_PERCENT`, etc. (voir `.env.example`).

### B. config.json (configuration de base, sans secrets)
Le module `app/config.py` charge ce fichier. Modifiez les indicateurs, les filtres et le risque, **sans toucher au code**. Exemple :
```json
{
  "symbol": "XAUUSD",
  "mode": "auto",
  "risk_percent": 1.5,
  "sl_atr_mult": 1.5,
  "tp_atr_mult": 3.0,
  "ema_h1_period": 200,
  "min_atr": 0.10,
  "news_impact": "High",
  "news_filter_enabled": true,
  "dashboard_password": ""
}
```
Copiez `config.example.json` en `config.json` et éditez.

### C. `.env` (pour Docker / hébergeurs)
```bash
MODE=auto
SYMBOL=XAUUSD
RISK_PERCENT=1.0
MAX_DAILY_DRAWDOWN_PCT=3.0
SL_ATR_MULT=1.5
TP_ATR_MULT=3.0
EMA_H1_PERIOD=200
MIN_ATR=0.10
MIN_ATR_RATIO=0.0002
NEWS_FILTER_ENABLED=1
NEWS_IMPACT=High
NEWS_CURRENCIES=USD,EUR
NEWS_BLOCK_BEFORE_MIN=30
NEWS_BLOCK_AFTER_MIN=30
PORT=8000
```

---

## 3. Utilisation avec un vrai compte MT5

### Prérequis
- Un compte **MT5** (DEMO recommandé pour commencer)
- Le client terminal **MetaTrader 5** installé et démarré (Windows/VPS)
- Le fichier `config.example.json` copié en `config.json` avec vos identifiants

### Configuration minimale en `MODE=live`
```bash
MT5_LOGIN=12345678
MT5_PASSWORD=votre_mot_de_passe
MT5_SERVER=NomDuServeurBroker
MODE=live
```

### Déroulé conseillé
| Étape | Rôle | Rappel de sécurité |
|---|---|---|
| 1. Compte démo | Validation du système (prix, ordres, P/L, filtres) | 100 % sûr |
| 2. Petite taille de lot sur démo | Validation du calcul du risque (1 %) et du sizing | 1 % de l'équité par trade |
| 3. Passage en vrai | Trading réel avec vos paramètres | Contrôle quotidien du drawdown, Panic Button à portée de main |

**Points de contrôle quotidiens** : solde, équité, P/L latent, drawdown du jour, spread, journal de bord, diagnostic moteur (tendance H1, RSI, ATR, bandes de Bollinger, verdict).

### Sécurités toujours actives
- **Circuit-breaker** : drawdown ≥ 3 % de l'équité du jour → liquidation totale + blocage jusqu'à minuit UTC
- **PANIC BUTTON** : double cliquement pour liquider immédiatement toutes les positions et désactiver le robot
- **Filtres** : news (blocage ±30 min autour des événements High USD/EUR), volatilité min (ATR), horaire de trading (7h–21h UTC par défaut)

---

## 4. API (pour le dashboard et les intégrations)

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Dashboard web |
| GET | `/api/state` | Snapshot complet (compte, equity, positions, logs, diagnostic) |
| GET | `/api/health` | Healthcheck hébergeur |
| POST | `/api/panic` | Liquidation totale + désactivation du robot |
| POST | `/api/bot/toggle` | `{"enabled": true/false}` |
| POST | `/api/filters` | `{"news": bool, "volatility": bool, "time": bool}` |
| POST | `/api/breaker/reset` | Réinitialise le circuit-breaker |

Le dashboard s'adapte à chaque seconde via `/api/state` (mise à jour en 1-2 s).

---

## 5. Déploiement sur un hébergeur gratuit

### Render (un clic)
1. Poussez le dépôt sur GitHub
2. Render → New → Blueprint (template `render.yaml`) → Apply
3. Renseignez les variables d'environnement dans l'interface du service
4. Le serveur démarre sur le plan free avec healthcheck `/api/health`

### Railway / Replit / autre
- Build : `Dockerfile` détecté automatiquement
- Start : `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Ajoutez les variables de `.env.example` dans l'interface de l'hébergeur
- Le port est injecté via `$PORT`

### Raccourci du manifeste
```bash
# Render → Blueprint
ls -la
git init && git add . && git commit -m "EliteBot" && git remote add origin <your-repo>
# Push, puis création du blueprint sur Render
```

---

## 6. Mécanisme quant (M5)

- **Tendance de fond** : prix > ou < EMA 200 H1 — long seulement au-dessus, short seulement en dessous
- **Momentum court** : RSI 14 + Bandes de Bollinger (20, 2σ) sur M5, pullback vers la bande extrême
- **Volatilité** : ATR 14 minimal absolu ET relatif — le marché plat bloque les trades
- **Gestion du risque** : taille de lot = 1 % de l'équité ÷ distance de stop (SL = 1,5×ATR, TP = 3×ATR, ratio 1:2)
- **Breakeven** : remontée du SL à l'entrée après +1×ATR en gain
- **Circuit-breaker** : drawdown ≥ 3 % → liquidation forcée, blocage jusqu'à minuit UTC
- **Filtre de news** : blocage ±30 min autour des événements Macro (USD/EUR) du calendrier ForexFactory

---

## 7. Sécurité

- Aucun secret dans le code ou le dépôt (`.gitignore` exclut `.env` et `config.json` si sensible)
- Les identifiants passent par les variables d'environnement uniquement
- Le circuit-breaker et le PANIC BUTTON opèrent côté serveur, indépendamment du dashboard
- Le dashboard est protégé si `DASHBOARD_PASSWORD` est défini

---

## 8. Dépannage

- **Console "Python non trouvé"** : installez Python depuis python.org et cochez "Add to PATH"
- **Dépendances incomplètes** : `pip install --upgrade pip && pip install -r requirements.txt`
- **Broker déconnecté** : vérifiez que le terminal MT5 est ouvert, que le mot de passe est correct, et que le serveur est bien celui demandé dans le terminal
- **Aucun signal** : vérifiez la fenêtre horaire (7h-21h UTC), la volatilité (ATR minimal), et les nouvelles (format USD/EUR, impact High)
- **Surcharge du serveur** : réduisez `POLL_INTERVAL` (minimum 1 s), et `MAX_LOTS` (max 10 lots)
- **Lecteur de fichier** : `python -m compileall -q app` pour contrôler la syntaxe
- **Mode nouveau** : `MODE=sim` pour simulation (démo, sans risque de perte)

---

## 9. Structure du projet (fichiers clés)

```
elitebot/
├── app/
│   ├── main.py               Serveur FastAPI (API + dashboard)
│   ├── trader.py             Boucle de trading (circuit-breaker, panic, breakeven)
│   ├── strategy.py           Stratégie hybride M5/H1 (RSI + BB + EMA200)
│   ├── indicators.py         RSI, Bollinger, EMA, ATR (numpy/pandas)
│   ├── broker.py             Pont MT5 natif (reconnexion infinie) + SimBroker (cloud)
│   ├── sim_clock.py          Générateur de marché M5/H1 réaliste (simulation)
│   ├── news.py               Filtre de news macro (±30 min via ForexFactory)
│   ├── state.py              État partagé thread-safe
│   ├── config.py             Configuration : env vars > config.json > défauts
│   └── static/               Dashboard : index.html, style.css, app.js
├── config.json               Configuration de base (sans secrets)
├── config.example.json       Exemple de config.json
├── .env.example              Variables d'environnement modèles
├── requirements.txt          Dépendances épinglées
├── Dockerfile                Image Docker optimisée
├── render.yaml               Blueprint Render (déploiement un clic)
├── Procfile                  Démarrage pour Replit/hebos sans Docker
├── start-elitebot.bat        Lancement Windows (installation automatique + bot)
├── start-elitebot.sh         Lancement macOS/Linux (même principe)
└── README.md                 Documentation complète
```

---

## À propos des fichiers inclus dans ce dépôt

| Fichier | Rôle |
|---|---|
| `app/main.py` | Serveur FastAPI, API, dashboard web |
| `app/trader.py` | Boucle de trading, circuit-breaker, panic, breakeven |
| `app/strategy.py` | Stratégie hybride M5/H1, RSI+Bollinger, EMA200, ATR |
| `app/indicators.py` | RSI, Bollinger, EMA, ATR |
| `app/broker.py` | Pont MetaTrader5 natif (reconnexion infinie) + SimBroker (simulation cloud) |
| `app/sim_clock.py` | Générateur de marché M5/H1 réaliste (mode simulation) |
| `app/news.py` | Filtre de news macro (±30 min) |
| `app/state.py` | État partagé thread-safe |
| `app/config.py` | Configuration (env vars > config.json > défauts) |
| `app/static/` | Dashboard (HTML/CSS/JS) |
| `config.json` | Configuration de base (à personnaliser) |
| `config.example.json` | Exemple de config.json |
| `.env.example` | Exemple de variables d'environnement |
| `requirements.txt` | Dépendances (versions épinglées) |
| `Dockerfile` | Image Docker optimisée |
| `render.yaml` | Blueprint Render (déploiement un clic) |
| `Procfile` | Démarrage pour Replit/hebos sans Docker |
| `start-elitebot.bat` | Lancement Windows (installation automatique + bot) |
| `start-elitebot.sh` | Lancement macOS/Linux (même principe) |
| `README.md` | Documentation complète |
