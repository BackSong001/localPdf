import re

from app.settings import load_settings


def test_tc_fr_013_a_health(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_tc_fr_013_b_version_format(client) -> None:
    version = client.get("/api/health").json()["version"]

    assert re.fullmatch(r"\d+\.\d+\.\d+", version)


def test_tc_fr_014_b_host_override() -> None:
    settings = load_settings({"LOCALPDF_HOST": "0.0.0.0"})

    assert settings.host == "0.0.0.0"


def test_tc_nfr_006_cors_allows_only_configured_origins(client) -> None:
    allowed = client.get(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    denied = client.get(
        "/api/health",
        headers={"Origin": "http://evil.example"},
    )

    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in denied.headers
