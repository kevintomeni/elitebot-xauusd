#!/usr/bin/env bash
# ============================================================================
#  EliteBot — Lancement et installation complet (macOS / Linux)
#  Placez ce fichier à la racine du projet, faites "chmod +x start-elitebot.sh",
#  puis lancez-le : ./start-elitebot.sh
# ============================================================================

set -euo pipefail

GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; NC="\033[0m"
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         EliteBot XAUUSD — Installation & lancement    ║${NC}"
echo -e "${GREEN}║         Trading quant automatisé pour OR (XAUUSD)     ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Détection de l'environnement ────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}ERROR${NC} python3 absent."; exit 1; }
command -v pip3  >/dev/null 2>&1 || { echo -e "${RED}ERROR${NC} pip3 absent.";   exit 1; }

PYTHON="python3"
PIP="pip3"
echo -e "[OK] ${GREEN}Python${NC} et ${GREEN}pip${NC} détectés."
echo ""

# ── 1. Installer les dépendances ────────────────────────────────────────────
echo "[Étape 1/6] Installation des dépendances..."
$PIP install --quiet --upgrade pip
$PIP install --quiet -r requirements.txt
echo "[OK] Dépendances installées."

# ── 2. Créer config.json si absent ─────────────────────────────────────────
echo "[Étape 2/6] Configuration du bot..."
if [ ! -f config.json ]; then
    cp config.example.json config.json
    echo "[OK] config.json créé à partir de config.example.json."
    echo "     Veuillez l'éditer (sed -i 's/.../.../' config.json) pour les identifiants."
fi

# ── 3. Demander les identifiants ───────────────────────────────────────────
echo "[Étape 3/6] Renseignement des identifiants MT5..."
read -p "  Numéro de compte MT5 (ou appuyez Entrée pour simulation) : " MT5_LOGIN
read -p "  Mot de passe MT5 : " MT5_PASSWORD
read -p "  Nom du serveur MT5 : " MT5_SERVER

if [ -n "$MT5_LOGIN" ] && [ -n "$MT5_PASSWORD" ] && [ -n "$MT5_SERVER" ]; then
    export MT5_LOGIN MT5_PASSWORD MT5_SERVER
    echo "[OK] Identifiants enregistrés temporairement."
else
    echo "[OK] Aucun identifiant fourni → mode simulation (sans risque)."
fi

# ── 4. Vérification des variables globales ────────────────────────────────
echo "[Étape 4/6] Configuration des variables d'environnement..."
if [ -z "${RISK_PERCENT:-}" ]; then
    export RISK_PERCENT=1.0
fi
if command -v bc >/dev/null 2>&1; then
    RISK_PERCENT=$(echo "$RISK_PERCENT" | bc -l 2>/dev/null || echo "1.0")
fi
export RISK_PERCENT

# ── 5. Lancement ───────────────────────────────────────────────────────────
echo "[Étape 5/6] Démarrage du serveur API + dashboard..."
echo ""
echo "  ── Mode de fonctionnement ──"
echo "  Mode : $( [ -n "$MT5_LOGIN" ] && echo "LIVE (terminal MT5 réel)" || echo "SIM / AUTO (démo)")"
echo "  Dashboard : http://localhost:8000"
echo "  API     : http://localhost:8000/api/state"
echo ""
echo "  ── À tester ──"
echo "  1) Ouvrez le dashboard dans un navigateur."
echo "  2) Vérifiez 'Broker connecté' et 'Prix XAUUSD'."
echo "  3) Activez le robot via 'Robot ON'."
echo ""
echo "[Étape 6/6] Lancement du serveur (2-3 s)..."
echo ""

export MT5_LOGIN MT5_PASSWORD MT5_SERVER
$PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8000
