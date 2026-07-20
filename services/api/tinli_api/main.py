import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tinli_api.datasource import readonly
from tinli_api.routes import router
from tinli_api.stream import StreamHub, get_hub, set_hub
from tinli_api.venues.kalshi_auth import KEY_ID_ENV, KEY_PATH_ENV, KalshiAuth


def demo_mode() -> bool:
    return os.environ.get("TINLI_DEMO", "0") == "1"


def stream_enabled() -> bool:
    """Live mode streams by default; demo stays socket-free (doctrine), and
    TINLI_STREAM=0 forces pure polling for debugging."""
    return not demo_mode() and os.environ.get("TINLI_STREAM", "1") != "0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub = None
    if stream_enabled():
        try:
            auth = KalshiAuth.from_env()
        except Exception:
            # a broken key file must not kill the app: stream without BYOK;
            # /v1/account reports the 422 with the config detail
            auth = None
        hub = StreamHub(kalshi_auth=auth)
        hub.start()
        set_hub(hub)
    yield
    if hub is not None:
        await hub.stop()
        set_hub(None)


app = FastAPI(title="tinli-api", version="0.1.0", lifespan=lifespan)
app.include_router(router)

# Hosted mode: serve the built terminal from the same process. In dev, vite
# serves the UI on :5173 and this mount simply doesn't exist (no dist/).
# Registered routes (/v1, /healthz) always win over the static mount.
DIST = Path(__file__).resolve().parents[3] / "apps" / "terminal" / "dist"


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "mode": "demo" if demo_mode() else "live",
        "readonly": readonly(),
        "stream": get_hub() is not None,
        # presence check only (no key file read): both env vars set and not
        # a read-only host. /v1/account is the authority on key validity.
        "byok": bool(os.environ.get(KEY_ID_ENV))
        and bool(os.environ.get(KEY_PATH_ENV))
        and not readonly(),
    }


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
