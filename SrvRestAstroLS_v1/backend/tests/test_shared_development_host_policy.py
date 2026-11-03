"""Static checks for automatic shared-host instructions; no services required."""
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
TELCHI_CONTEXT = "SrvRestAstroLS_v1/backend/modules/telchi/CONTEXT.md"


def _section(path: str, heading: str, next_heading: str | None = None) -> str:
    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    section = source.split(heading, 1)[1]
    return section.split(next_heading, 1)[0] if next_heading else section


def test_root_instructions_reach_telchi_host_policy() -> None:
    root = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    context = (REPO_ROOT / TELCHI_CONTEXT).read_text(encoding="utf-8")
    assert TELCHI_CONTEXT in root
    assert "antes de elegir directorios" in root
    assert "`SHARED_HOST_SAFETY`: aplicar siempre la sección 19" in context
    assert "incluso si el prompt solo pide ejecutar un gate" in context


@pytest.mark.parametrize("path,heading,next_heading", [
    ("AGENTS.md", "## Shared development host", "## Ownership y concurrencia"),
    (TELCHI_CONTEXT, "## 19. Shared development host safety", None),
])
def test_host_policies_protect_processes_and_allow_available_capacity(
    path: str, heading: str, next_heading: str | None,
) -> None:
    policy = _section(path, heading, next_heading)
    for contract in (
        "USE AVAILABLE CAPACITY, DO NOT DESTABILIZE THE HOST",
        "CORRECTNESS > HOST STABILITY > SPEED",
        "concurrencia moderada",
        "NO terminar procesos que la ejecución actual no haya creado",
        "killall", "pkill", "RESOURCE_BLOCKED", "ENVIRONMENTAL_ABORT",
        "FUNCTIONAL_FAILURE", "swap", "single-thread",
    ):
        assert contract in policy


def test_telchi_promotions_require_preflight_and_safe_cleanup() -> None:
    policy = _section(TELCHI_CONTEXT, "## 19. Shared development host safety")
    assert "Toda promoción Foundation requiere resource preflight" in policy
    assert "`BLOCKED_HOST`" in policy
    assert "no es test failure" in policy
    assert "Si hay dudas, dejar intacto" in policy
    assert "OWN_PROCESSES_LEFT_RUNNING" in policy
    assert "runtime/resource_guard.py" in policy
    assert "no autoriza ignorarlos ni elevar límites para obtener PASS" in policy


def test_project_skill_respects_existing_server_ownership() -> None:
    skill = (REPO_ROOT / ".agents/skills/team360-project/SKILL.md").read_text(
        encoding="utf-8",
    )
    assert "respetar `AGENTS.md` sección Shared development host" in skill
    assert "bajar solo servidores creados por la ejecución actual" in skill
    assert "el agente puede bajar/subir esos dos servidores locales" not in skill
