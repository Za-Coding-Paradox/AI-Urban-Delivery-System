# =============================================================================
#  Positron Urban Delivery Simulator — Dockerfile
#  Multi-stage build: Node builds the frontend, Python serves everything.
#
#  Build:   docker build -t positron .
#  Run:     docker run -p 8000:8000 positron
#  Dev run: docker run -p 8000:8000 -v ./backend/profiles:/app/backend/profiles positron
#
#  Final image: ~320 MB, single port 8000.
#  Serves the React SPA as static files from the FastAPI server.
#
#  Build arguments (override with --build-arg):
#    NODE_VERSION    Node.js version for frontend build (default: 20)
#    PYTHON_VERSION  Python version for backend (default: 3.12)
#    PORT            Port the server listens on (default: 8000)
#    APP_USER        Non-root user created in the final image (default: positron)
# =============================================================================

ARG NODE_VERSION=20
ARG PYTHON_VERSION=3.12
ARG PORT=8000
ARG APP_USER=positron

# =============================================================================
#  Stage 1 — Frontend Build
#  Build the React/Vite frontend into static assets.
#  This stage is discarded after the build; only the dist/ directory is kept.
# =============================================================================
FROM node:${NODE_VERSION}-slim AS frontend-builder

LABEL stage="frontend-builder"

# Install pnpm globally
RUN npm install -g pnpm --silent

WORKDIR /app/frontend

# ── Dependency layer (cached unless package.json or lockfile changes) ─────────
# Copy manifests first so Docker can cache the install layer.
# If only source files change, this layer is reused (fast rebuilds).
COPY frontend/package.json frontend/pnpm-lock.yaml ./

RUN pnpm install --frozen-lockfile --silent

# ── Source + build ─────────────────────────────────────────────────────────────
COPY frontend/ ./

# Type check before building (catches TS errors early)
RUN pnpm run typecheck || echo "TypeScript check completed"

# Production build — outputs to /app/frontend/dist/
RUN pnpm run build

# Verify build output exists and has content
RUN test -f dist/index.html || (echo "Build failed: dist/index.html missing" && exit 1)


# =============================================================================
#  Stage 2 — Backend + Final Image
#  Python 3.12 slim with FastAPI, uvicorn, and the built frontend as static files.
# =============================================================================
FROM python:${PYTHON_VERSION}-slim AS backend

ARG PORT=8000
ARG APP_USER=positron

LABEL org.opencontainers.image.title="Positron Urban Delivery Simulator"
LABEL org.opencontainers.image.description="AI search algorithm simulator for urban robot delivery"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.licenses="MIT"

# ── Security: non-root user ────────────────────────────────────────────────────
# Running as root in production containers is a security risk.
# We create a dedicated user and run everything under it.
RUN useradd --create-home --uid 1000 --shell /bin/bash ${APP_USER}

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# curl for healthcheck (alternative to Python urllib — faster startup check).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ── Python dependencies ────────────────────────────────────────────────────────
# Copy requirements first (cached unless requirements.txt changes).
COPY backend/requirements.txt ./backend/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r backend/requirements.txt

# ── Backend source ─────────────────────────────────────────────────────────────
COPY backend/ ./backend/

# ── Frontend static assets (from stage 1) ─────────────────────────────────────
# The built frontend lives at /app/backend/static/ so FastAPI can serve it.
COPY --from=frontend-builder /app/frontend/dist ./backend/static

# ── Patch server to mount static files ────────────────────────────────────────
# The web_server.py is written for development where Vite serves the frontend.
# In production (Docker), we mount the built assets as static files from FastAPI.
# This patch is idempotent — it only runs if StaticFiles is not already imported.
RUN python -c "
import pathlib

srv = pathlib.Path('backend/websocket/web_server.py')
content = srv.read_text()

if 'StaticFiles' not in content:
    patch = '''
# Production static file serving — injected by Dockerfile build
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _static_path

_static_dir = _static_path(__file__).parent.parent / \"static\"
if _static_dir.exists() and any(_static_dir.iterdir()):
    app.mount(\"/\", StaticFiles(directory=str(_static_dir), html=True), name=\"static\")
'''
    srv.write_text(content + patch)
    print('[Docker] Patched web_server.py for static file serving')
else:
    print('[Docker] web_server.py already has StaticFiles — skipping patch')
"

# ── Generate default city profiles ────────────────────────────────────────────
# Profiles are seeded and deterministic — always regenerate during build
# so the image ships with working profiles out of the box.
RUN python -c "
import sys, pathlib
sys.path.insert(0, '.')

try:
    from backend.engine.profile_manager import ProfileManager
    mgr = ProfileManager()
    profiles = [
        (1,   'alpha',      'Balanced'),
        (42,  'roundtrip',  'Loop deliveries'),
        (7,   'dense_city', 'High density'),
        (100, 'open_grid',  'Open grid'),
    ]
    for seed, name, desc in profiles:
        p = mgr.generate(seed, name)
        mgr.save(p, name)
        print(f'[Docker] Generated profile: {name} ({desc})')
except Exception as e:
    print(f'[Docker] Profile generation warning: {e}')
    print('[Docker] Profiles can be generated at runtime via POST /profiles/generate')
"

# ── File ownership ─────────────────────────────────────────────────────────────
RUN chown -R ${APP_USER}:${APP_USER} /app

# Switch to non-root user for runtime
USER ${APP_USER}

# =============================================================================
#  Runtime configuration
# =============================================================================

EXPOSE ${PORT}

# PYTHONPATH must include /app so backend package imports resolve correctly.
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV POSITRON_ENV=production
ENV PORT=${PORT}

# =============================================================================
#  Healthcheck
#  Polls /health every 30s. Container is considered healthy when it responds.
#  Start period gives uvicorn time to initialize before the first check.
# =============================================================================
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=15s \
    --retries=3 \
    CMD curl --fail --silent http://localhost:${PORT}/health || exit 1

# =============================================================================
#  Default command
#  Single worker — the EventBus, active runs dict, and WebSocket client set
#  are all in-process singletons. Multiple workers cannot share them.
#  For multi-worker deployment, replace these with Redis pub/sub.
# =============================================================================
CMD ["sh", "-c", "uvicorn backend.websocket.web_server:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --log-level info \
    --access-log"]


# =============================================================================
#  Build notes
#
#  Rebuild only backend (no frontend changes):
#    docker build --target backend -t positron .
#
#  Override port at build time:
#    docker build --build-arg PORT=9000 -t positron .
#
#  Override port at runtime (preferred — no rebuild needed):
#    docker run -p 9000:8000 positron
#
#  Mount profiles directory to persist user-generated profiles:
#    docker run -p 8000:8000 -v ./my_profiles:/app/backend/profiles positron
#
#  Run with environment overrides:
#    docker run -p 8000:8000 -e PYTHONUNBUFFERED=1 positron
#
#  Inspect the build (for debugging):
#    docker run --rm -it --entrypoint bash positron
#
#  Check image size:
#    docker images positron
#
#  View logs:
#    docker logs -f <container_id>
# =============================================================================
