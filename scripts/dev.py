"""Run the API (uvicorn :8000) and terminal UI (vite :5173) together.

Invoked by `make dev` / `make demo`. Ctrl+C stops both.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # terminate() only kills the direct child; uvicorn's reloader and
        # npm both wrap the real server in a child process that would
        # survive and hold the port. /T takes the whole tree down.
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        proc.terminate()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--demo",
        action="store_true",
        help="boot from recorded fixtures with the SIMULATED DATA badge",
    )
    args = parser.parse_args()

    if not VENV_PY.exists():
        sys.exit("no .venv found — run `make setup` first")
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm not found on PATH")

    env = os.environ.copy()
    if args.demo:
        env["TINLI_DEMO"] = "1"
        print("[dev] demo mode: SIMULATED DATA (market fixtures land in M1)")

    procs = [
        subprocess.Popen(
            [str(VENV_PY), "-m", "uvicorn", "tinli_api.main:app", "--reload", "--port", "8000"],
            cwd=ROOT,
            env=env,
        ),
        subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "apps" / "terminal", env=env),
    ]

    exit_code = 0
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        exit_code = next(p.returncode for p in procs if p.poll() is not None)
        print(f"[dev] a process exited with code {exit_code}; shutting down")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            stop(p)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
