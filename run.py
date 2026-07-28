"""One-command start — the only prerequisite is Python 3.12+ and Node.

    python run.py           live mode
    python run.py demo      recorded fixtures (SIMULATED DATA badge)

First run bootstraps everything (venv, Python deps, npm install) and takes
a few minutes; later runs skip straight to boot. `make` is NOT required —
the Makefile keeps working for those who prefer it.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")


def run(desc: str, cmd: list[str], **kw) -> None:
    print(f"-> {desc}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT, **kw)
    if result.returncode != 0:
        sys.exit(f"FAILED: {desc} (exit {result.returncode})")


def ensure_venv() -> None:
    if not VENV_PY.exists():
        if sys.version_info < (3, 12):
            sys.exit(f"Python 3.12+ required (this is {sys.version.split()[0]})")
        run("creating virtualenv (.venv)", [sys.executable, "-m", "venv", ".venv"])
    # editable installs are cheap to re-run and pick up new dependencies;
    # only do the slow path when a first-party package is missing
    probe = subprocess.run(
        [str(VENV_PY), "-c", "import tinli_api, tinli_backtest"], capture_output=True, cwd=ROOT
    )
    if probe.returncode != 0:
        run("installing Python packages", [str(VENV_PY), "-m", "pip", "install", "-q",
                                           "-r", "requirements-dev.txt"])


def ensure_npm() -> None:
    if not (ROOT / "apps" / "terminal" / "node_modules").is_dir():
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run("installing UI packages (npm)", [npm, "install", "--no-fund", "--no-audit"],
            cwd=ROOT / "apps" / "terminal")


def main() -> None:
    demo = len(sys.argv) > 1 and sys.argv[1] == "demo"
    ensure_venv()
    ensure_npm()
    args = [str(VENV_PY), str(ROOT / "scripts" / "dev.py")] + (["--demo"] if demo else [])
    print(f"-> starting tinli ({'demo — SIMULATED DATA' if demo else 'live'}) "
          f"at http://localhost:5173", flush=True)
    os.execv(str(VENV_PY), args) if os.name != "nt" else sys.exit(
        subprocess.run(args, cwd=ROOT).returncode
    )


if __name__ == "__main__":
    main()
