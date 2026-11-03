"""Build/install/import Srv05 outside the checkout, without editable packages.

Run: uv run python scripts/validate_srv05_wheel.py --output <new-directory>
Optional --offline uses only uv's cache. Does not start lifespan/automation.
Temporary environments are always removed; evidence and wheels are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

BACKEND = Path(__file__).resolve().parents[1]
REQUIRED = ("ls_iMotorSoft_Srv05.py", "ls_iMotorSoft_Srv01.py", "globalVar.py")
PROBE = r'''
import asyncio, importlib, json, pathlib, socket, sys
from unittest.mock import patch
root = pathlib.Path(sys.prefix).resolve()
source = pathlib.Path(sys.argv[1]).resolve()
assert not any(source == pathlib.Path(p).resolve() or source in pathlib.Path(p).resolve().parents for p in sys.path if p)
for pth in root.glob("lib/python*/site-packages/*.pth"):
    assert "editable" not in pth.name.lower(), str(pth)
def forbidden(*args, **kwargs):
    raise AssertionError("Import/factory attempted external network I/O")
with patch.object(socket.socket, "connect", forbidden):
    modules = {name: importlib.import_module(name) for name in ("ls_iMotorSoft_Srv05", "ls_iMotorSoft_Srv01", "globalVar")}
    origins = {name: str(pathlib.Path(mod.__file__).resolve()) for name, mod in modules.items()}
    assert all(root in pathlib.Path(p).parents and "site-packages" in pathlib.Path(p).parts for p in origins.values()), origins
    srv, legacy, config = (modules[n] for n in ("ls_iMotorSoft_Srv05", "ls_iMotorSoft_Srv01", "globalVar"))
    assert srv.app is legacy.app and srv.create_app is legacy.create_app
    assert config.SERVICE_NAME == "backend-team360" and callable(config.get_team360_db_url)
    fresh = srv.create_app()
    schema = fresh.openapi_schema.to_schema()
    rows = [(path, method) for path, item in schema["paths"].items() for method in item if method in {"get", "post", "patch", "put", "delete", "head"}]
    assert len(rows) == len(set(rows)) and ("/health", "get") in rows
    async def health():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fresh), base_url="http://test") as client:
            result = await client.get("/health")
            assert result.status_code == 200
            return result.json()
    payload = asyncio.run(health())
# Installed Uvicorn command smoke, not production lifecycle certification.
import subprocess, time, urllib.request
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
command = [sys.executable, "-I", "-m", "uvicorn", "ls_iMotorSoft_Srv05:app", "--host", "127.0.0.1", "--port", str(port), "--lifespan", "off"]
with open("installed-uvicorn.log", "w+") as log:
    worker = subprocess.Popen(command, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    assert response.status == 200
                    assert json.load(response)["status"] == "ok"
                break
            except OSError:
                if worker.poll() is not None or time.monotonic() >= deadline:
                    raise AssertionError("Installed Uvicorn failed to listen")
                time.sleep(0.1)
    finally:
        if worker.poll() is None:
            worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=5)
    log.seek(0)
    listener = {"command": command, "pid": worker.pid, "port": port, "health": "PASS", "cleanup": "PASS", "logs": log.read()}
print(json.dumps({"status": "PASS", "origins": origins, "cwd": str(pathlib.Path.cwd()), "operations": len(rows), "health": payload, "lifespan_started": False, "installed_listener": listener}))
'''


def validate(output: Path, offline: bool = False) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        env.pop(key, None)
    # Structural mode: no lifecycle, DB, retrieval, or quota consumption.
    env.update(AUTOMATION_DIAGNOSIS_REPOSITORY="memory", TEAM360_AI_PROVIDER="mock",
               TEAM360_DIAGNOSIS_STATE_PROVIDER="memory", TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER="mock")
    commands = []
    report = {"status": "FAIL", "commands": commands}
    outside = None
    def run(argv, cwd, name, timeout=240):
        commands.append(argv)
        result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        (output / name).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"{name}: exit {result.returncode}")
        return result.stdout
    try:
        run(["uv", "build", "--wheel", "--out-dir", str(output)], BACKEND, "build.log")
        wheel, = output.glob("*.whl")
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
        (output / "contents.txt").write_text("\n".join(names) + "\n")
        assert all(name in names for name in REQUIRED), "Required runtime modules absent"
        assert not any(name.endswith((".env", ".pem", ".key")) for name in names), "Private file in artifact"
        report.update(wheel=wheel.name, sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), members=len(names))
        # Reuse the reviewed lock without installing the checkout/editable project.
        requirements = output / "requirements.txt"
        run(["uv", "export", "--frozen", "--no-emit-project", "--no-editable",
             "--output-file", str(requirements)], BACKEND, "export.log")
        with tempfile.TemporaryDirectory(prefix="srv05-wheel-") as temp:
            outside = Path(temp)
            venv = outside / "venv"
            run(["uv", "venv", "--python", sys.executable, str(venv)], outside, "venv.log")
            python = venv / "bin/python"
            command = ["uv", "pip", "install", "--python", str(python), "-r", str(requirements), str(wheel)]
            if offline:
                command.append("--offline")
            run(command, outside, "install.log")
            probe = run([str(python), "-I", "-c", PROBE, str(BACKEND)], outside, "import.log", 60)
            report.update(isolated=json.loads(probe.strip().splitlines()[-1]), status="PASS")
        report["temporary_environment_removed"] = not outside.exists()
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if outside is not None:
            report["temporary_environment_removed"] = not outside.exists()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = validate(args.output, args.offline)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
