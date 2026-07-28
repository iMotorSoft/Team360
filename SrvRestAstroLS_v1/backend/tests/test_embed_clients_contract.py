from __future__ import annotations

from pathlib import Path

from modules.embed_clients.auth import resolve_request_origin
from modules.embed_clients.hmac import build_canonical_string, sign, verify


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_embed_clients_migration_exists():
    path = _backend_root() / "db" / "migrations" / "008_create_embed_clients.sql"
    assert path.exists()
    assert path.is_file()


def test_embed_clients_migration_contains_expected_contract():
    sql = (
        _backend_root()
        / "db"
        / "migrations"
        / "008_create_embed_clients.sql"
    ).read_text(encoding="utf-8")
    assert "create table if not exists embed_clients" in sql.lower()
    assert "client_id" in sql
    assert "hmac_secret" in sql
    assert "allowed_origins" in sql
    assert "idx_ec_client_id" in sql
    assert "idx_ec_is_active" in sql
    assert "chk_ec_allowed_origins_is_array" in sql


def test_embed_clients_seed_example_exists():
    path = (
        _backend_root()
        / "db"
        / "migrations"
        / "008_create_embed_clients_seed_example.sql"
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "NOT applied automatically" in content
    assert "embed-secret-key-change-in-production" in content


def test_embed_hmac_sign_and_verify():
    canonical = build_canonical_string(
        client_id="demo_client",
        timestamp=1_710_000_000,
        session_id="embed_session",
        message="Quiero automatizar ventas",
    )
    signature = sign(canonical, "secret-123")
    assert verify(canonical, "secret-123", signature) is True
    assert verify(canonical, "wrong-secret", signature) is False


def test_resolve_request_origin_prefers_origin_header():
    resolved = resolve_request_origin(
        "https://app.cliente.com",
        "https://other.example/path?x=1",
    )
    assert resolved == "https://app.cliente.com"


def test_resolve_request_origin_falls_back_to_referer_origin():
    resolved = resolve_request_origin(
        None,
        "https://cliente.com/landing/embed?campaign=test",
    )
    assert resolved == "https://cliente.com"


def test_mamamia360_seed_exists():
    path = (
        _backend_root()
        / "db"
        / "migrations"
        / "009_seed_mamamia360_embed_client.sql"
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "mamamia360" in content
    assert "mamamia360-embed-secret-change-in-production" in content
    assert "https://mamamia360.com" in content


def test_mamamia360_demo_and_docs_contain_client_id():
    project_root = _backend_root().parent
    for target_path in [
        "astro/public/embed-demo/mamamia360.html",
        "docs/mamamia360-embed-snippet.md",
    ]:
        path = project_root / target_path
        assert path.exists(), f"Missing: {target_path}"
        content = path.read_text(encoding="utf-8")
        assert "mamamia360" in content, f"Missing clientId in {target_path}"
        assert "hmac_secret" not in content, f"Leak in {target_path}"


def test_mamamia360_public_snippets_no_secret_leak():
    project_root = _backend_root().parent
    for snippet_path in [
        "astro/public/embed/vera-loader.js",
        "astro/public/embed-demo/mamamia360.html",
    ]:
        path = project_root / snippet_path
        assert path.exists(), f"Missing: {snippet_path}"
        content = path.read_text(encoding="utf-8")
        assert "hmac_secret" not in content, f"Leak in {snippet_path}"
        assert "mamamia360-embed-secret" not in content, f"Leak in {snippet_path}"
