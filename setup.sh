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
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      MAJOR=$(echo "$VER" | cut -d. -f1)
      MINOR=$(echo "$VER" | cut -d. -f2)
      if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
        PYTHON="$cmd"
        ok "Python $VER found ($cmd)"
        return 0
      fi
    fi
  done
  fail "Python 3.11+ not found."
}

check_node() {
  if ! command -v node &>/dev/null; then fail "Node.js not found."; fi
  VER=$(node -v | sed 's/v//')
  MAJOR=$(echo "$VER" | cut -d. -f1)
  if [ "$MAJOR" -lt 18 ]; then fail "Node.js $VER found but v18+ required"; fi
  ok "Node.js v$VER found"
}

check_pnpm() {
  if ! command -v pnpm &>/dev/null; then fail "pnpm not found. Please install via 'npm install -g pnpm'"; fi
  ok "pnpm $(pnpm -v) found"
}

check_python
check_node
check_pnpm

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
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
info "Installing Python dependencies…"
pip install -r backend/requirements.txt --quiet
ok "Python dependencies installed"

# ── Node.js dependencies (Bulletproof) ────────────────────────────────────────
head "Setting up Node.js environment"
cd frontend

info "Attempting strict install (frozen-lockfile)..."
# Temporarily turn off strict error checking so the script doesn't crash here
set +e 
pnpm install --frozen-lockfile --silent > /dev/null 2>&1
INSTALL_EXIT_CODE=$?
set -e # Turn strict checking back on

if [ $INSTALL_EXIT_CODE -eq 0 ]; then
  ok "Dependencies installed successfully."
else
  warn "Lockfile mismatch detected. Auto-fixing and updating lockfile..."
  pnpm install --silent
  ok "Dependencies installed and lockfile updated."
fi
cd ..

# ── schema files check ────────────────────────────────────────────────────────
head "Checking schema files"
SCHEMAS=("cell.schema.json" "city_profile.schema.json" "algorithm_config.schema.json" "robot_config.schema.json" "deliver_sequence.schema.json" "metrics_summary.schema.json" "trace_event.schema.json")
for s in "${SCHEMAS[@]}"; do
  if [ -f "backend/schemas/$s" ]; then
    ok "$s"
  fi
done

# ── generate default profiles ─────────────────────────────────────────────────
head "Generating default city profiles"
export PYTHONPATH="$SCRIPT_DIR"
$PYTHON - <<'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    from backend.engine.profile_manager import ProfileManager
    import pathlib
    mgr = ProfileManager()
    for seed, name in [(1, "alpha"), (42, "roundtrip"), (7, "dense_city"), (100, "open_grid")]:
        existing = pathlib.Path(f"backend/profiles/{name}.json")
        if not existing.exists():
            p = mgr.generate(seed, name)
            mgr.save(p, name)
            print(f"  ✓  {name} generated")
        else:
            print(f"  ✓  {name} exists")
except Exception as e:
    print(f"  ⚠  Generation skipped: {e}")
PYEOF

# ── frontend build (prod only) ────────────────────────────────────────────────
if [ "$MODE" = "prod" ]; then
  head "Building frontend (production)"
  cd frontend
  pnpm run build
  cd ..
  rm -rf backend/static/*
  cp -r frontend/dist/* backend/static/
  ok "Frontend assets deployed to backend/static/"
fi

# ── write .env file ───────────────────────────────────────────────────────────
cat > .env <<EOF
POSITRON_HOST=0.0.0.0
POSITRON_PORT=8000
POSITRON_ENV=${MODE}
PYTHONPATH=${SCRIPT_DIR}
EOF

# ── run tests ─────────────────────────────────────────────────────────────────
head "Running test suite"
if python -m pytest backend/tests/ -q --tb=short 2>&1 | tail -5; then
  ok "All tests passed"
else
  warn "Some tests failed — check above output"
fi

# ── launch instructions ───────────────────────────────────────────────────────
head "Setup complete"

if [ "$MODE" = "dev" ]; then
  echo -e "  ${CYAN}Terminal 1 (backend):${RESET} source .venv/bin/activate && export PYTHONPATH=\$PWD && uvicorn backend.websocket.web_server:app --reload --port 8000"
  echo -e "  ${CYAN}Terminal 2 (frontend):${RESET} cd frontend && pnpm run dev"
  echo ""
  
  echo -e "${YELLOW}Auto-launch both servers now? [y/N]${RESET} "
  read -r -t 10 LAUNCH || LAUNCH="n"
  if [[ "$LAUNCH" =~ ^[Yy]$ ]]; then
    source .venv/bin/activate
    export PYTHONPATH=$PWD
    uvicorn backend.websocket.web_server:app --reload --port 8000 --log-level warning &
    BACKEND_PID=$!
    cd frontend && pnpm run dev &
    FRONTEND_PID=$!
    echo ""
    info "Press Ctrl+C to stop both servers"
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT
    wait
  fi
fi
