"""Static checks on docker-compose.yml and the Dockerfile.

Docker isn't needed to run these. They catch the wiring mistakes that would
otherwise only show up on a fresh `docker compose up`: a service started
before the seed has finished, a command pointing at a module that doesn't
exist, or a secret baked into the image.
"""
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
APP_SERVICES = ["seed", "app", "scheduler", "api"]


@pytest.mark.parametrize("name", APP_SERVICES)
def test_command_targets_an_importable_module(name):
    command = SERVICES[name]["command"]
    assert command[:2] == ["python", "-m"]
    assert importlib.util.find_spec(command[2]) is not None, command[2]


@pytest.mark.parametrize("name", ["app", "scheduler", "api"])
def test_runtime_services_wait_for_seed_to_finish(name):
    assert SERVICES[name]["depends_on"]["seed"]["condition"] == "service_completed_successfully"


def test_seed_waits_for_healthy_postgres():
    assert SERVICES["seed"]["depends_on"]["postgres"]["condition"] == "service_healthy"


@pytest.mark.parametrize("name", APP_SERVICES)
def test_app_services_point_at_the_compose_postgres_host(name):
    url = SERVICES[name]["environment"]["DATABASE_URL"]
    assert "@postgres:5432/" in url  # service name, not localhost


def test_scheduler_restarts_but_one_shots_do_not():
    assert SERVICES["scheduler"]["restart"] == "unless-stopped"
    assert SERVICES["seed"]["restart"] == "no"
    assert SERVICES["app"]["restart"] == "no"


def test_app_services_share_one_image():
    images = {SERVICES[n]["image"] for n in APP_SERVICES}
    assert len(images) == 1


def test_dockerfile_runs_as_non_root_and_uses_runtime_requirements_only():
    lines = [l.strip() for l in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()]
    instructions = [l for l in lines if l and not l.startswith("#")]
    assert "USER appuser" in instructions
    assert any(l.startswith("COPY requirements.txt") for l in instructions)
    assert not any("requirements-dev" in l for l in instructions)


def test_dockerignore_keeps_secrets_and_tests_out_of_the_image():
    lines = {l.strip() for l in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    assert {".env", ".git", "tests"} <= lines


def test_runtime_requirements_exclude_dev_tools():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pytest" not in runtime and "pyyaml" not in runtime
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "-r requirements.txt" in dev and "pytest" in dev


@pytest.mark.parametrize("name", ["postgres", "postgres_test"])
def test_initdb_mounts_only_the_schema_file(name):
    """initdb runs every .sql in its directory alphabetically and aborts on the
    first error. Mounting the whole sql/ folder would run analytics_examples.sql
    before schema.sql and fail on a fresh volume."""
    mounts = [v for v in SERVICES[name]["volumes"] if "docker-entrypoint-initdb.d" in v]
    assert len(mounts) == 1
    source = mounts[0].split(":")[0]
    assert source == "./sql/schema.sql", f"mount only the schema file, not {source}"


def test_api_service_exposes_8000_and_has_a_healthcheck():
    api = SERVICES["api"]
    assert "127.0.0.1:8000:8000" in api["ports"], "publish the API on localhost only"
    assert "API_KEY" in api["environment"]
    assert api["restart"] == "unless-stopped"
    assert "/health" in " ".join(api["healthcheck"]["test"])
    # the ASGI target in the command must really exist
    from src.api.main import app
    assert api["command"][3] == "src.api.main:app" and app is not None


@pytest.mark.parametrize("name", ["app", "scheduler"])
def test_pipeline_services_write_the_lake_to_a_named_volume(name):
    svc = SERVICES[name]
    assert "lake:/lake" in svc["volumes"]
    assert svc["environment"]["LAKE_DIR"] == "/lake"
    assert "lake" in COMPOSE["volumes"]


def test_dockerfile_creates_a_lake_dir_the_non_root_user_can_write():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "mkdir /lake" in text and "chown appuser:appuser /lake" in text
    # ownership must be set BEFORE dropping privileges
    assert text.index("chown appuser:appuser /lake") < text.index("USER appuser")


def test_web_and_parquet_dependencies_are_runtime_not_dev():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert all(pkg in runtime for pkg in ("fastapi", "uvicorn", "pyarrow"))
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "httpx" in dev and "httpx" not in runtime
