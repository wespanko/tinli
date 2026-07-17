import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tinli_api.datasource import readonly
from tinli_api.routes import router

app = FastAPI(title="tinli-api", version="0.1.0")
app.include_router(router)

# Hosted mode: serve the built terminal from the same process. In dev, vite
# serves the UI on :5173 and this mount simply doesn't exist (no dist/).
# Registered routes (/v1, /healthz) always win over the static mount.
DIST = Path(__file__).resolve().parents[3] / "apps" / "terminal" / "dist"


def demo_mode() -> bool:
    return os.environ.get("TINLI_DEMO", "0") == "1"


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "mode": "demo" if demo_mode() else "live",
        "readonly": readonly(),
    }


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
