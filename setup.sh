#!/usr/bin/env bash
# =============================================================================
#  Positron Urban Delivery Simulator — Setup Script
#  Supports: macOS, Linux (Ubuntu/Debian, Fedora/RHEL, Arch)
#
#  Usage:
#    bash setup.sh [MODE] [OPTIONS]
#
#  Modes:
#    --dev      Development mode: venv + deps + profiles + tests (default)
#    --prod     Production mode: builds frontend, deploys to backend/static/
#    --docker   Build and launch Docker container
#    --clean    Remove all generated files (venv, node_modules, dist, profiles)
#    --fresh    Clean everything then run --dev (full fresh install)
#
#  Options:
#    --no-tests     Skip running the test suite
#    --no-launch    Skip the auto-launch prompt
#    --port PORT    Backend port (default: 8000)
#    --help, -h     Show this help message
# =============================================================================
set -euo pipefail
IFS=$'\n\t'

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

ok()    { echo -e "${GREEN}  ✓${RESET}  $*"; }
info()  { echo -e "${CYAN}  ›${RESET}  $*"; }
warn()  { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
fail()  { echo -e "${RED}  ✗  $*${RESET}"; exit 1; }
step()  { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════${RESET}"; echo -e "${BOLD}${CYAN}  $*${RESET}"; echo -e "${BOLD}${CYAN}══════════════════════════════════════${RESET}"; }
banner(){ echo -e "${BOLD}${CYAN}$*${RESET}"; }

# ── argument parsing ──────────────────────────────────────────────────────────
MODE="dev"
RUN_TESTS=true
AUTO_LAUNCH=true
PORT=8000

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)       MODE="dev"    ;;
    --prod)      MODE="prod"   ;;
    --docker)    MODE="docker" ;;
    --clean)     MODE="clean"  ;;
    --fresh)     MODE="fresh"  ;;
    --no-tests)  RUN_TESTS=false ;;
    --no-launch) AUTO_LAUNCH=false ;;
    --port)      shift; PORT="$1" ;;
    --help|-h)
      echo ""
      echo -e "${BOLD}Positron Urban Delivery Simulator — Setup Script${RESET}"
      echo ""
      echo "  Usage: bash setup.sh [MODE] [OPTIONS]"
      echo ""
      echo "  Modes:"
      echo "    --dev      Development mode (default)"
      echo "    --prod     Production mode — builds frontend"
      echo "    --docker   Docker build + run"
      echo "    --clean    Remove all generated artifacts"
      echo "    --fresh    Clean then install fresh (--clean + --dev)"
      echo ""
      echo "  Options:"
      echo "    --no-tests     Skip running the test suite"
      echo "    --no-launch    Skip the auto-launch prompt"
      echo "    --port PORT    Backend port (default: 8000)"
      echo "    --help, -h     Show this help"
      echo ""
      exit 0
      ;;
    *) warn "Unknown argument: $1 (ignored)" ;;
  esac
  shift
done

# ── resolve script directory ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON=""

# ── banner ────────────────────────────────────────────────────────────────────
echo ""
banner "  ╔══════════════════════════════════════════════════╗"
banner "  ║        Positron Urban Delivery Simulator         ║"
banner "  ║        AI Search Algorithm Simulator v0.1        ║"
banner "  ╚══════════════════════════════════════════════════╝"
echo ""
info "Mode   : ${BOLD}${MODE}${RESET}"
info "Port   : ${BOLD}${PORT}${RESET}"
info "Tests  : ${BOLD}${RUN_TESTS}${RESET}"
echo ""

# =============================================================================
#  CLEAN MODE — remove all generated artifacts
# =============================================================================
clean_artifacts() {
  step "Cleaning generated artifacts"

  local removed=0

  if [ -d ".venv" ]; then
    rm -rf .venv
    ok "Removed .venv/"
    ((removed++))
  fi

  if [ -d "frontend/node_modules" ]; then
    rm -rf frontend/node_modules
    ok "Removed frontend/node_modules/"
    ((removed++))
  fi

  if [ -d "frontend/dist" ]; then
    rm -rf frontend/dist
    ok "Removed frontend/dist/"
    ((removed++))
  fi

  if [ -d "backend/static" ]; then
    rm -rf backend/static
    ok "Removed backend/static/"
    ((removed++))
  fi

  # Generated profiles (keep schema files)
  if [ -d "backend/profiles" ]; then
    local count
    count=$(find backend/profiles -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$count" -gt 0 ]; then
      rm -f backend/profiles/*.json
      ok "Removed $count generated profile(s) from backend/profiles/"
      ((removed++))
    fi
  fi

  if [ -f ".env" ]; then
    rm -f .env
    ok "Removed .env"
    ((removed++))
  fi

  # Python cache
  find . -type d -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
  find . -type d -name ".pytest_cache" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
  find . -type d -name ".ruff_cache"   -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
  find . -name "*.pyc" -not -path "./.git/*" -delete 2>/dev/null || true
  ok "Removed Python cache files"

  if [ "$removed" -eq 0 ]; then
    info "Nothing to clean — workspace is already fresh"
  else
    ok "Clean complete"
  fi
}

if [ "$MODE" = "clean" ]; then
  clean_artifacts
  echo ""
  ok "Done. Run 'bash setup.sh --dev' to reinstall."
  exit 0
fi

if [ "$MODE" = "fresh" ]; then
  clean_artifacts
  MODE="dev"
fi

# =============================================================================
#  DOCKER MODE
# =============================================================================
if [ "$MODE" = "docker" ]; then
  step "Docker build and run"

  if ! command -v docker &>/dev/null; then
    fail "Docker not found. Install from https://docs.docker.com/get-docker/"
  fi

  ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

  info "Building Docker image: positron:latest"
  docker build -t positron:latest .
  ok "Image built successfully"

  # Stop any existing container
  if docker ps -q --filter name=positron-app | grep -q .; then
    info "Stopping existing positron-app container..."
    docker stop positron-app >/dev/null
    docker rm positron-app >/dev/null
  fi

  info "Starting container on port ${PORT}..."
  docker run -d \
    --name positron-app \
    -p "${PORT}:8000" \
    --restart unless-stopped \
    positron:latest

  echo ""
  ok "Container started!"
  echo ""
  info "  App:    ${BOLD}http://localhost:${PORT}${RESET}"
  info "  API:    ${BOLD}http://localhost:${PORT}/docs${RESET}"
  info "  Health: ${BOLD}http://localhost:${PORT}/health${RESET}"
  echo ""
  info "  Logs:   docker logs -f positron-app"
  info "  Stop:   docker stop positron-app"
  exit 0
fi

# =============================================================================
#  PREREQUISITES
# =============================================================================
step "Checking prerequisites"

# Python 3.11+
check_python() {
  for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null) || continue
      local major minor
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
        PYTHON="$cmd"
        ok "Python $ver ($cmd)"
        return 0
      else
        warn "Found Python $ver via $cmd — need 3.11+"
      fi
    fi
  done

  echo ""
  fail "Python 3.11+ not found. Install from https://python.org or use pyenv."
}

# Node 18+
check_node() {
  if ! command -v node &>/dev/null; then
    fail "Node.js not found. Install from https://nodejs.org (v18+)"
  fi
  local ver
  ver=$(node -v | sed 's/v//')
  local major
  major=$(echo "$ver" | cut -d. -f1)
  if [ "$major" -lt 18 ]; then
    fail "Node.js v$ver found but v18+ is required."
  fi
  ok "Node.js v$ver"
}

# pnpm
check_pnpm() {
  if ! command -v pnpm &>/dev/null; then
    warn "pnpm not found — attempting to install via npm..."
    if command -v npm &>/dev/null; then
      npm install -g pnpm --silent
      ok "pnpm installed via npm"
    else
      fail "Neither pnpm nor npm found. Install pnpm from https://pnpm.io/installation"
    fi
  else
    ok "pnpm $(pnpm --version)"
  fi
}

check_python
check_node
check_pnpm

# =============================================================================
#  DIRECTORY STRUCTURE
# =============================================================================
step "Ensuring directory structure"
mkdir -p backend/profiles
mkdir -p backend/schemas
mkdir -p backend/static
mkdir -p backend/tests
ok "Directories ready"

# =============================================================================
#  PYTHON VIRTUAL ENVIRONMENT
# =============================================================================
step "Python virtual environment"

if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtual environment at .venv/ ..."
  "$PYTHON" -m venv "$VENV_DIR"
  ok "Virtual environment created"
else
  ok ".venv/ exists — reusing"
fi

# Activate
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# Upgrade pip silently
info "Upgrading pip..."
pip install --upgrade pip --quiet --no-warn-script-location

# Install dependencies
info "Installing Python dependencies..."
if pip install -r backend/requirements.txt --quiet --no-warn-script-location; then
  ok "Python dependencies installed"
else
  fail "pip install failed. Check backend/requirements.txt and your internet connection."
fi

# =============================================================================
#  NODE.JS DEPENDENCIES
# =============================================================================
step "Node.js dependencies (frontend)"

cd frontend

# Try frozen lockfile first (CI-safe), fall back to auto-update
info "Installing frontend dependencies..."
set +e
pnpm install --frozen-lockfile --silent 2>/dev/null
PNPM_EXIT=$?
set -e

if [ "$PNPM_EXIT" -eq 0 ]; then
  ok "Frontend dependencies installed (frozen lockfile)"
else
  warn "Lockfile mismatch — updating lockfile and installing..."
  pnpm install --silent
  ok "Frontend dependencies installed (lockfile updated)"
fi

cd "$SCRIPT_DIR"

# =============================================================================
#  SCHEMA VALIDATION
# =============================================================================
step "Validating schema files"

SCHEMAS=(
  "cell.schema.json"
  "city_profile.schema.json"
  "algorithm_config.schema.json"
  "robot_config.schema.json"
  "deliver_sequence.schema.json"
  "metrics_summary.schema.json"
  "trace_event.schema.json"
)

MISSING=0
for s in "${SCHEMAS[@]}"; do
  if [ -f "backend/schemas/$s" ]; then
    ok "$s"
  else
    warn "Missing schema: backend/schemas/$s"
    ((MISSING++))
  fi
done

if [ "$MISSING" -gt 0 ]; then
  warn "$MISSING schema file(s) missing — some validation may be skipped"
fi

# =============================================================================
#  DEFAULT CITY PROFILES
# =============================================================================
step "Generating default city profiles"

export PYTHONPATH="$SCRIPT_DIR"

"$PYTHON" - <<'PYEOF'
import sys
import pathlib

sys.path.insert(0, '.')

try:
    from backend.engine.profile_manager import ProfileManager

    mgr = ProfileManager()
    profiles = [
        (1,   "alpha",      "Balanced — moderate obstacles"),
        (42,  "roundtrip",  "Deliveries form a loop"),
        (7,   "dense_city", "High obstacle density"),
        (100, "open_grid",  "Open grid with traffic zones"),
    ]

    for seed, name, description in profiles:
        path = pathlib.Path(f"backend/profiles/{name}.json")
        if path.exists():
            print(f"  ✓  {name} — already exists, skipping")
        else:
            p = mgr.generate(seed, name)
            mgr.save(p, name)
            print(f"  ✓  {name} — generated ({description})")

except Exception as e:
    print(f"  ⚠  Profile generation skipped: {e}")
    print(f"     You can generate profiles manually via the API: POST /profiles/generate")
PYEOF

# =============================================================================
#  FRONTEND BUILD (prod only)
# =============================================================================
if [ "$MODE" = "prod" ]; then
  step "Building frontend (production)"

  cd frontend
  info "Running pnpm build..."
  pnpm run build
  cd "$SCRIPT_DIR"

  info "Deploying frontend assets to backend/static/ ..."
  rm -rf backend/static
  mkdir -p backend/static
  cp -r frontend/dist/* backend/static/
  ok "Frontend assets deployed to backend/static/"

  # Patch server to serve static files if not already patched
  if ! grep -q "StaticFiles" backend/websocket/web_server.py; then
    info "Patching web_server.py to serve static files..."
    cat >> backend/websocket/web_server.py <<'PATCH'

# Static file serving (production build)
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path
_static_dir = _Path(__file__).parent.parent / "static"
if _static_dir.exists() and any(_static_dir.iterdir()):
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
PATCH
    ok "web_server.py patched for static file serving"
  fi
fi

# =============================================================================
#  WRITE .ENV FILE
# =============================================================================
step "Writing environment file"

cat > .env <<EOF
# Positron Urban Delivery Simulator — Environment Configuration
# Generated by setup.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")

POSITRON_HOST=0.0.0.0
POSITRON_PORT=${PORT}
POSITRON_ENV=${MODE}
PYTHONPATH=${SCRIPT_DIR}
EOF

ok ".env written"

# =============================================================================
#  TEST SUITE
# =============================================================================
if [ "$RUN_TESTS" = "true" ]; then
  step "Running test suite"

  export PYTHONPATH="$SCRIPT_DIR"
  set +e
  PYTEST_OUT=$("$PYTHON" -m pytest backend/tests/ -q --tb=short 2>&1)
  PYTEST_EXIT=$?
  set -e

  echo "$PYTEST_OUT" | tail -10

  if [ "$PYTEST_EXIT" -eq 0 ]; then
    ok "All tests passed"
  else
    warn "Some tests failed — see output above"
    warn "The app may still work, but investigate before deploying"
  fi
else
  info "Tests skipped (--no-tests)"
fi

# =============================================================================
#  GENERATE LAUNCH HELPERS
# =============================================================================
step "Writing launch helper scripts"

cat > run_backend.sh <<SCRIPT
#!/usr/bin/env bash
# Start the Positron backend server (development mode with hot reload)
cd "$(pwd)"
source .venv/bin/activate
export PYTHONPATH=\$(pwd)
exec uvicorn backend.websocket.web_server:app \\
  --reload \\
  --host 0.0.0.0 \\
  --port ${PORT} \\
  --log-level info
SCRIPT
chmod +x run_backend.sh
ok "run_backend.sh"

cat > run_frontend.sh <<SCRIPT
#!/usr/bin/env bash
# Start the Positron frontend development server (Vite HMR)
cd "$(pwd)/frontend"
exec pnpm dev
SCRIPT
chmod +x run_frontend.sh
ok "run_frontend.sh"

if [ "$MODE" = "prod" ]; then
  cat > run_prod.sh <<SCRIPT
#!/usr/bin/env bash
# Start the Positron production server (serves frontend + backend on one port)
cd "$(pwd)"
source .venv/bin/activate
export PYTHONPATH=\$(pwd)
exec uvicorn backend.websocket.web_server:app \\
  --host 0.0.0.0 \\
  --port ${PORT} \\
  --workers 1 \\
  --log-level info
SCRIPT
  chmod +x run_prod.sh
  ok "run_prod.sh"
fi

# =============================================================================
#  COMPLETION SUMMARY
# =============================================================================
step "Setup complete"

echo ""
if [ "$MODE" = "dev" ]; then
  echo -e "  ${BOLD}Development mode — two servers required:${RESET}"
  echo ""
  echo -e "  ${CYAN}Backend  (Terminal 1):${RESET}"
  echo -e "    ${DIM}bash run_backend.sh${RESET}"
  echo -e "    ${DIM}# or: source .venv/bin/activate && export PYTHONPATH=\$PWD && uvicorn backend.websocket.web_server:app --reload --port ${PORT}${RESET}"
  echo ""
  echo -e "  ${CYAN}Frontend (Terminal 2):${RESET}"
  echo -e "    ${DIM}bash run_frontend.sh${RESET}"
  echo -e "    ${DIM}# or: cd frontend && pnpm dev${RESET}"
  echo ""
  echo -e "  ${CYAN}Open:${RESET} ${BOLD}http://localhost:5173${RESET}  (frontend)"
  echo -e "  ${CYAN}API:${RESET}  ${BOLD}http://localhost:${PORT}/docs${RESET}"
  echo ""

  if [ "$AUTO_LAUNCH" = "true" ]; then
    echo -e "  ${YELLOW}Auto-launch both servers now? [y/N]${RESET} "
    read -r -t 15 LAUNCH || LAUNCH="n"
    if [[ "$LAUNCH" =~ ^[Yy]$ ]]; then
      echo ""
      info "Starting backend on port ${PORT}..."
      source .venv/bin/activate
      export PYTHONPATH=$SCRIPT_DIR
      uvicorn backend.websocket.web_server:app \
        --reload \
        --host 0.0.0.0 \
        --port "$PORT" \
        --log-level warning &
      BACKEND_PID=$!

      info "Starting frontend (Vite)..."
      cd frontend && pnpm dev &
      FRONTEND_PID=$!
      cd "$SCRIPT_DIR"

      echo ""
      ok "Both servers started!"
      echo ""
      info "  Frontend: ${BOLD}http://localhost:5173${RESET}"
      info "  Backend:  ${BOLD}http://localhost:${PORT}${RESET}"
      info "  API docs: ${BOLD}http://localhost:${PORT}/docs${RESET}"
      echo ""
      info "  Press ${BOLD}Ctrl+C${RESET} to stop both servers"
      trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; ok 'Servers stopped.'" INT TERM
      wait
    fi
  fi

elif [ "$MODE" = "prod" ]; then
  echo -e "  ${BOLD}Production mode — single server:${RESET}"
  echo ""
  echo -e "  ${CYAN}Start:${RESET}"
  echo -e "    ${DIM}bash run_prod.sh${RESET}"
  echo ""
  echo -e "  ${CYAN}Open:${RESET} ${BOLD}http://localhost:${PORT}${RESET}"
  echo -e "  ${CYAN}API:${RESET}  ${BOLD}http://localhost:${PORT}/docs${RESET}"
  echo ""
fi
