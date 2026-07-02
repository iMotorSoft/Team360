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
