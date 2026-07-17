# Tinli hosted instance: one container = API + built UI + history recorder.
# Read-only by default (TINLI_READONLY=1): positions editing disabled, the
# shipped example book demos the risk engine.

# --- UI build ---
FROM node:22-slim AS ui
WORKDIR /repo/apps/terminal
COPY apps/terminal/package.json apps/terminal/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY apps/terminal ./
RUN npm run build

# --- runtime ---
FROM python:3.12-slim
WORKDIR /repo
COPY packages ./packages
COPY services ./services
COPY scripts ./scripts
COPY data ./data
# editable installs keep the repo layout live: datasource resolves
# data/event_map.yaml and friends relative to the source tree
RUN pip install --no-cache-dir \
    -e ./packages/schema -e ./packages/risk -e ./packages/divergence \
    -e ./services/api
COPY --from=ui /repo/apps/terminal/dist ./apps/terminal/dist

ENV TINLI_READONLY=1 \
    TINLI_HISTORY_DIR=/data/history \
    TINLI_USER_AGENT="tinli/0.1 (+https://tinli.dev)"

EXPOSE 8080
# recorder in the background (60s cadence, survives venue outages), API in
# the foreground as PID 1
CMD ["sh", "-c", "python scripts/snapshot.py --loop 60 & exec uvicorn tinli_api.main:app --host 0.0.0.0 --port 8080"]
