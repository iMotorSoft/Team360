"""Execute copies of the real DEV launchers with inert command boundaries.

No services, ports, private override files or original scripts are changed.
These are launcher contracts, not a full-stack/browser gate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]


def _executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o700)


def _environment(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "ss", "#!/bin/sh\nexit 0\n")
    _executable(bin_dir / "timeout", "#!/bin/sh\nexit 0\n")
    _executable(bin_dir / "curl", f"#!{sys.executable}\n" + '''
import pathlib, sys
args = sys.argv[1:]
pathlib.Path(args[args.index('--output') + 1]).write_text(
    '{"data":[{"id":"openai_gpt-5.4-nano"}]}')
print('200', end='')
''')
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", TEAM360_DEV_PROFILE="normal",
               TEAM360_BACKEND_HOST="127.0.0.1", TEAM360_BACKEND_PORT="17050",
               TEAM360_LITELLM_BASE_URL="http://127.0.0.1:4000",
               AUTOMATION_DIAGNOSIS_REPOSITORY="postgres",
               ASTRO_HOST="127.0.0.1", ASTRO_PORT="13050",
               TEST_LAUNCH_RECORD=str(tmp_path / "launch.jsonl"))
    return env


RECORD = '''
import json, os, pathlib, sys
with pathlib.Path(os.environ['TEST_LAUNCH_RECORD']).open('a') as f:
    f.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd(),
                       'repository': os.getenv('AUTOMATION_DIAGNOSIS_REPOSITORY')}) + '\\n')
'''


def test_backend_launcher_preserves_srv01_asgi_command_and_working_directory(tmp_path):
    env = _environment(tmp_path)
    shutil.copyfile(PROJECT / "backend-dev.sh", tmp_path / "backend-dev.sh")
    _executable(tmp_path / "backend/.venv/bin/uvicorn", f"#!{sys.executable}\n" + RECORD)
    result = subprocess.run(["bash", str(tmp_path / "backend-dev.sh")], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    record = json.loads((tmp_path / "launch.jsonl").read_text())
    assert record["args"] == ["ls_iMotorSoft_Srv01:app", "--host", "127.0.0.1",
                              "--port", "17050"]
    assert record["cwd"] == str(tmp_path)
    assert record["repository"] == "postgres"
    # The launcher does not cd into backend or export a backend PYTHONPATH in
    # normal mode. Its real launch depends on the environment's module lookup.
    assert "Application: ls_iMotorSoft_Srv01:app" in result.stdout


def test_astro_launcher_builds_embed_assets_then_runs_dev_config(tmp_path):
    env = _environment(tmp_path)
    shutil.copyfile(PROJECT / "astro-dev.sh", tmp_path / "astro-dev.sh")
    global_js = tmp_path / "astro/src/components/global.js"
    global_js.parent.mkdir(parents=True)
    shutil.copyfile(PROJECT / "astro/src/components/global.js", global_js)
    _executable(tmp_path / "bin/npx", f"#!{sys.executable}\n" + RECORD)
    _executable(tmp_path / "bin/node", "#!/bin/sh\nexit 0\n")
    result = subprocess.run(["bash", str(tmp_path / "astro-dev.sh")], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in (tmp_path / "launch.jsonl").read_text().splitlines()]
    assert [r["args"] for r in records] == [
        ["astro", "build"],
        ["astro", "dev", "--config", "astro.config.dev.mjs",
         "--host", "127.0.0.1", "--port", "13050"],
    ]
    assert all(r["cwd"] == str(tmp_path / "astro") for r in records)
