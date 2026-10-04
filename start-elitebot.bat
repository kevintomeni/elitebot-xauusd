@echo off
REM ============================================================================
REM  EliteBot — Lancement et installation complet (Windows)
REM  Copiez ce fichier dans le dossier du projet et double-cliquez pour démarrer.
REM  L'application sera accessible sur http://localhost:8000
REM ============================================================================

title EliteBot Launcher

echo.
echo  ╔═══════════════════════════════════════════════════════╗
echo  ║         EliteBot XAUUSD — Mode d'installation         ║
echo  ║         Trading quant automatisé pour OR (XAUUSD)     ║
echo  ╚═══════════════════════════════════════════════════════╝
echo.

REM ── Détection de l'environnement ──────────────────────────────────────────
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas installé. Téléchargez-en une version moderne :
    echo           https://www.python.org/downloads/
    pause
    exit /b 1
)

where pip >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERREUR] pip n'est pas installé. Installez-le via "python -m ensurepip".
    pause
    exit /b 1
)

set PYTHON=python
set PIP=pip

echo [OK] Python et pip détectés.
echo.

REM ── Vérification du dossier de travail ─────────────────────────────────────
if not exist "app" (
    echo [ERREUR] Ce script doit être exécuté à la racine du projet (dossier
    echo          contenant le dossier "app" et le fichier "requirements.txt").
    pause
    exit /b 1
)

REM ── 1. Installation des dépendances ───────────────────────────────────────
echo [Étape 1/6] Installation des dépendances Python...
call %PIP% install --quiet --upgrade pip
call %PIP% install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERREUR] Échec de l'installation des dépendances.
    pause
    exit /b 1
)
echo [OK] Dépendances installées (FastAPI, uvicorn, pandas, numpy, MetaTrader5).

REM ── 2. Création du fichier de configuration ───────────────────────────────
echo [Étape 2/6] Configuration du bot...
if not exist "config.json" (
    copy "config.example.json" "config.json" >nul 2>&1
    echo [OK] Fichier config.json créé à partir de config.example.json.
    echo       Veuillez l'éditer pour y saisir vos identifiants (voir étape 3).
) else (
    echo [OK] config.json existe déjà.
)

REM ── 3. Renseignement des identifiants (si non fournis par env vars) ───────
echo [Étape 3/6] Renseignement des identifiants MT5...
set MT5_LOGIN=%%MT5_LOGIN%%
set MT5_PASSWORD=%%MT5_PASSWORD%%
set MT5_SERVER=%%MT5_SERVER%%
set MODE=auto

if "%MT5_LOGIN%"=="" (
    set /p MT5_LOGIN="  Numéro de compte MT5 (démo/exemple: 12345678) : "
)
if "%MT5_PASSWORD%"=="" (
    set /p MT5_PASSWORD="  Mot de passe MT5 : "
)
if "%MT5_SERVER%"=="" (
    set /p MT5_SERVER="  Nom du serveur MT5 (ex: Weltrade-Demo) : "
)

echo [OK] Identification prête (secret non affiché).
echo.

REM ── 4. Vérification des variables d'environnement globales ────────────────
echo [Étape 4/6] Configuration des variables d'environnement globales...
set /a RISK_PERCENT=%%RISK_PERCENT%%
set /a RISK_PERCENT=%RISK_PERCENT%
if %RISK_PERCENT% leq 0 set RISK_PERCENT=1.0

REM ── 5. Lancement du serveur ──────────────────────────────────────────────
echo [Étape 5/6] Démarrage du serveur API + dashboard...
echo.
echo  ── Mode de fonctionnement ──
if "%MODE%"=="live" (
    echo  Mode LIVE  : connexion au terminal MT5 réel (votre compte).
    echo  PAUSE  : ne
    echo           mettez pas le terminal en mode "Expert Advisor"
    echo           ou laissez-le ouvert avec les identifiants correctes.
) else (
    echo  Mode SIM / AUTO  : simulation de marché si MT5 absent
    echo  (démo, sans risque de perte).
)
echo.
echo  ── Dashboard ──
echo  Interface : http://localhost:8000
echo  API state : http://localhost:8000/api/state
echo.
echo  ── À tester ──
echo  1) Ouvrez le dashboard dans un navigateur.
echo  2) Vérifiez "Broker connecté" et "Prix XAUUSD".
echo  3) Si connexion réussie, activez le robot via le bouton "Robot ON".
echo.
echo [ÉTAPE 6/6] Attente du démarrage du serveur (2-3 secondes)...
echo.

REM Configuration des variables d'environnement pour ce processus
set MT5_LOGIN=%MT5_LOGIN%
set MT5_PASSWORD=%MT5_PASSWORD%
set MT5_SERVER=%MT5_SERVER%

call %PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port 8000
if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] Le serveur s'est arrêté.
    pause
)
