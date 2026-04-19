#!/usr/bin/env bash
# =============================================================================
#  Positron Urban Delivery Simulator — Setup Script
#  Supports: macOS, Linux (Ubuntu/Debian, Fedora, Arch)
#  Usage:    bash setup.sh [--dev | --prod | --docker]
# =============================================================================
set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  ✓${RESET}  $*"; }
info() { echo -e "${CYAN}  ›${RESET}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
fail() { echo -e "${RED}  ✗${RESET}  $*"; exit 1; }
head() { echo -e "\n${BOLD}${CYAN}══ $* ${RESET}"; }

# ── argument parsing ──────────────────────────────────────────────────────────
MODE="dev"   # dev | prod | docker
for arg in "$@"; do
  case "$arg" in
    --dev)    MODE="dev"    ;;
    --prod)   MODE="prod"   ;;
    --docker) MODE="docker" ;;
    --help|-h)
      echo "Usage: bash setup.sh [--dev | --prod | --docker]"
      echo "  --dev     Development mode (Vite dev server + uvicorn)"
      echo "  --prod    Production mode (build frontend, serve via uvicorn)"
      echo "  --docker  Build and run Docker container"
      exit 0
      ;;
    *) warn "Unknown argument: $arg (ignored)" ;;
  esac
done

# ── banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════╗"
echo "  ║   Positron Urban Delivery Simulator           ║"
echo "  ║   AI Search Algorithm Simulator v0.1          ║"
echo "  ╚═══════════════════════════════════════════════╝"
echo -e "${RESET}"
info "Mode: ${BOLD}${MODE}${RESET}"
echo ""

# ── prerequisite checks ───────────────────────────────────────────────────────
head "Checking prerequisites"

check_python() {
  # Try python3, then python
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      MAJOR=$(echo "$VER" | cut -d. -f1)
      MINOR=$(echo "$VER" | cut -d. -f2)
      if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
        PYTHON="$cmd"
        ok "Python $VER found ($cmd)"
        return 0
      else
        warn "Python $VER found but 3.11+ required"
      fi
    fi
  done
  fail "Python 3.11+ not found. Install from https://python.org"
}

check_node() {
  if ! command -v node &>/dev/null; then
    fail "Node.js not found. Install from https://nodejs.org (v18+ required)"
  fi
  VER=$(node -v | sed 's/v//')
  MAJOR=$(echo "$VER" | cut -d. -f1)
  if [ "$MAJOR" -lt 18 ]; then
    fail "Node.js $VER found but v18+ required"
  fi
  ok "Node.js v$VER found"
}

check_npm() {
  if ! command -v npm &>/dev/null; then
    fail "npm not found. Install Node.js from https://nodejs.org"
  fi
  ok "npm $(npm -v) found"
}

check_python
check_node
check_npm

if [ "$MODE" = "docker" ]; then
  if ! command -v docker &>/dev/null; then
    fail "Docker not found. Install from https://docker.com"
  fi
  ok "Docker $(docker -v | awk '{print $3}' | tr -d ,) found"
fi

# ── directory structure ───────────────────────────────────────────────────────
head "Ensuring directory structure"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p backend/profiles
mkdir -p backend/schemas
mkdir -p backend/static
ok "Directories ready"

# ── Python virtual environment ────────────────────────────────────────────────
head "Setting up Python environment"

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtual environment at .venv/"
  $PYTHON -m venv "$VENV_DIR"
  ok "Virtual environment created"
else
  ok "Virtual environment exists"
fi

# Activate
source "$VENV_DIR/bin/activate"
ok "Virtual environment activated"

# Upgrade pip silently
info "Upgrading pip…"
pip install --upgrade pip --quiet
ok "pip upgraded"

# Install Python dependencies
info "Installing Python dependencies…"
pip install -r requirements.txt --quiet
ok "Python dependencies installed"

# ── Node.js dependencies ──────────────────────────────────────────────────────
head "Setting up Node.js environment"

if [ -f "package-lock.json" ]; then
  info "Installing Node.js dependencies (npm ci)…"
  npm ci --silent
else
  info "Installing Node.js dependencies (npm install)…"
  npm install --silent
fi
ok "Node.js dependencies installed"

# ── schema files check ────────────────────────────────────────────────────────
head "Checking schema files"

SCHEMAS=(
  "cell.schema.json"
  "city_profile.schema.json"
  "algorithm_config.schema.json"
  "robot_config.schema.json"
  "deliver_sequence.schema.json"
  "metrics_summary.schema.json"
  "trace_event.schema.json"
)

SCHEMAS_OK=true
for s in "${SCHEMAS[@]}"; do
  if [ -f "backend/schemas/$s" ]; then
    ok "$s"
  elif [ -f "$s" ]; then
    # Copy from project root if found there
    cp "$s" "backend/schemas/$s"
    ok "$s (copied to backend/schemas/)"
  else
    warn "Missing schema: $s (will be auto-located at runtime)"
    SCHEMAS_OK=false
  fi
done

# ── generate default profiles ─────────────────────────────────────────────────
head "Generating default city profiles"

$PYTHON - <<'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    from backend.engine.profile_manager import ProfileManager
    import json, pathlib

    mgr = ProfileManager()
    for seed, name in [(1, "alpha"), (42, "roundtrip"), (7, "dense_city"), (100, "open_grid")]:
        try:
            existing = pathlib.Path(f"backend/profiles/{name}.json")
            if existing.exists():
                print(f"  ✓  {name} (exists)")
            else:
                p = mgr.generate(seed, name)
                mgr.save(p, name)
                print(f"  ✓  {name} (seed={seed})")
        except Exception as e:
            print(f"  ⚠  {name}: {e}")
except ImportError as e:
    print(f"  ⚠  Could not generate profiles: {e}")
PYEOF

# ── frontend build (prod only) ────────────────────────────────────────────────
if [ "$MODE" = "prod" ]; then
  head "Building frontend (production)"
  info "Running npm run build…"
  npm run build
  ok "Frontend built"

  # Copy dist into backend/static
  info "Copying dist/ → backend/static/"
  rm -rf backend/static/*
  cp -r dist/* backend/static/
  ok "Frontend assets deployed to backend/static/"

  # Patch web_server.py to mount StaticFiles if not already done
  if ! grep -q "StaticFiles" backend/websocket/web_server.py 2>/dev/null; then
    info "Patching web_server.py to serve static frontend…"
    cat >> backend/websocket/web_server.py <<'PATCH'

# ── Static frontend (production) ──────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path
_static_dir = _Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
PATCH
    ok "web_server.py patched for static file serving"
  fi
fi

# ── Docker mode ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
  head "Building Docker image"

  if [ ! -f "Dockerfile" ]; then
    fail "Dockerfile not found. Run 'bash setup.sh --prod' first or create Dockerfile."
  fi

  info "Building image: positron:latest"
  docker build -t positron:latest .
  ok "Docker image built"

  echo ""
  info "Run with: docker run -p 8000:8000 positron:latest"
  exit 0
fi

# ── write .env file ───────────────────────────────────────────────────────────
head "Writing environment config"

cat > .env <<EOF
# Positron environment — generated by setup.sh
POSITRON_HOST=0.0.0.0
POSITRON_PORT=8000
POSITRON_ENV=${MODE}
PYTHONPATH=${SCRIPT_DIR}
EOF
ok ".env written"

# ── run tests ─────────────────────────────────────────────────────────────────
head "Running test suite"

info "pytest backend tests…"
if python -m pytest backend/tests/ -q --tb=short 2>&1 | tail -5; then
  ok "All tests passed"
else
  warn "Some tests failed — check above output"
fi

# ── launch instructions / auto-launch ─────────────────────────────────────────
head "Setup complete"

echo ""
if [ "$MODE" = "dev" ]; then
  echo -e "${BOLD}Development mode — start with:${RESET}"
  echo ""
  echo -e "  ${CYAN}Terminal 1 (backend):${RESET}"
  echo "    source .venv/bin/activate"
  echo "    uvicorn backend.websocket.web_server:app --reload --port 8000"
  echo ""
  echo -e "  ${CYAN}Terminal 2 (frontend):${RESET}"
  echo "    npm run dev"
  echo ""
  echo -e "  ${CYAN}Then open:${RESET} http://localhost:5173"
  echo ""

  # Offer to start both automatically
  echo -e "${YELLOW}Auto-launch both servers now? [y/N]${RESET} "
  read -r -t 10 LAUNCH || LAUNCH="n"
  if [[ "$LAUNCH" =~ ^[Yy]$ ]]; then
    source .venv/bin/activate
    uvicorn backend.websocket.web_server:app --reload --port 8000 --log-level warning &
    BACKEND_PID=$!
    sleep 1
    npm run dev &
    FRONTEND_PID=$!
    ok "Backend PID: $BACKEND_PID"
    ok "Frontend PID: $FRONTEND_PID"
    echo ""
    info "Press Ctrl+C to stop both servers"
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT
    wait
  fi

elif [ "$MODE" = "prod" ]; then
  echo -e "${BOLD}Production mode — start with:${RESET}"
  echo ""
  echo "    source .venv/bin/activate"
  echo "    uvicorn backend.websocket.web_server:app --host 0.0.0.0 --port 8000"
  echo ""
  echo -e "  ${CYAN}Then open:${RESET} http://localhost:8000"
  echo ""
fi

echo -e "${GREEN}${BOLD}Positron is ready.${RESET}"
echo ""
