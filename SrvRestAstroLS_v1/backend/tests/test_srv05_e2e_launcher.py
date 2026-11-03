"""Inert launcher boundary checks: never start services."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from test_srv05_launchers import _environment, _executable, RECORD, PROJECT


@pytest.mark.parametrize("env_name,value", [("TEAM360_ENV", "production"), ("TEAM360_BACKEND_HOST", "0.0.0.0"), ("TEAM360_E2E_EVIDENCE", "")])
def test_e2e_launcher_rejects_unsafe_configuration(tmp_path, env_name, value):
    env = _environment(tmp_path)
    env.update(TEAM360_DEV_PROFILE="srv05-e2e", TEAM360_ENV="development", TEAM360_E2E_EVIDENCE=str(tmp_path / "evidence.json"))
    env[env_name] = value
    shutil.copyfile(PROJECT / "backend-dev.sh", tmp_path / "backend-dev.sh")
    result = subprocess.run(["bash", str(tmp_path / "backend-dev.sh")], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not (tmp_path / "launch.jsonl").exists()


def test_e2e_launcher_selects_test_harness_only(tmp_path):
    env = _environment(tmp_path)
    env.update(TEAM360_DEV_PROFILE="srv05-e2e", TEAM360_ENV="development", TEAM360_E2E_EVIDENCE=str(tmp_path / "evidence.json"))
    shutil.copyfile(PROJECT / "backend-dev.sh", tmp_path / "backend-dev.sh")
    _executable(tmp_path / "backend/.venv/bin/python", f"#!{sys.executable}\n" + RECORD)
    result = subprocess.run(["bash", str(tmp_path / "backend-dev.sh")], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    record = json.loads((tmp_path / "launch.jsonl").read_text())
    assert record["args"] == [str(tmp_path / "backend/scripts/srv05_e2e_runtime.py")]
