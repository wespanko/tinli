import os

from fastapi import FastAPI

app = FastAPI(title="tinli-api", version="0.1.0")


def demo_mode() -> bool:
    return os.environ.get("TINLI_DEMO", "0") == "1"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "mode": "demo" if demo_mode() else "live"}
