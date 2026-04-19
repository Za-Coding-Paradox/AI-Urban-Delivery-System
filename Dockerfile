# =============================================================================
#  Positron Urban Delivery Simulator — Dockerfile
#  Multi-stage build: Node builds the frontend, Python serves everything.
#  Final image: ~320 MB, single port 8000.
# =============================================================================

# ── Stage 1: Frontend build ───────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

# Install pnpm
RUN npm install -g pnpm

WORKDIR /app/frontend

# Install dependencies first (layer cache)
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --silent

# Copy source and build
COPY frontend/ ./
RUN pnpm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.12-slim AS backend

# Security: non-root user
RUN useradd -m -u 1000 positron

WORKDIR /app

# Install Python deps (layer cache)
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/frontend/dist ./backend/static

# Patch web_server.py to mount static files
RUN python -c "
import pathlib
srv = pathlib.Path('backend/websocket/web_server.py')
content = srv.read_text()
if 'StaticFiles' not in content:
    patch = '''
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path
_static = _Path(__file__).parent.parent / \"static\"
if _static.exists():
    app.mount(\"/\", StaticFiles(directory=str(_static), html=True), name=\"static\")
'''
    srv.write_text(content + patch)
    print('Patched web_server.py for static file serving')
"

# Generate default profiles
RUN python -c "
import sys; sys.path.insert(0,'.')
try:
    from backend.engine.profile_manager import ProfileManager
    mgr = ProfileManager()
    for seed, name in [(1,'alpha'),(42,'roundtrip'),(7,'dense_city'),(100,'open_grid')]:
        p = mgr.generate(seed, name); mgr.save(p, name)
        print(f'Generated profile: {name}')
except Exception as e:
    print(f'Profile generation skipped: {e}')
"

# Set ownership
RUN chown -R positron:positron /app
USER positron

# ── Runtime ────────────────────────────────────────────────────────────────────
EXPOSE 8000

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.websocket.web_server:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--log-level", "info", "--workers", "1"]
