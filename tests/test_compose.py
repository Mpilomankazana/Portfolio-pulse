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
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
SERVICES = COMPOSE["services"]
APP_SERVICES = ["seed", "app", "scheduler"]


@pytest.mark.parametrize("name", APP_SERVICES)
def test_command_targets_an_importable_module(name):
    command = SERVICES[name]["command"]
    assert command[:2] == ["python", "-m"]
    assert importlib.util.find_spec(command[2]) is not None, command[2]


@pytest.mark.parametrize("name", ["app", "scheduler"])
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
    lines = [l.strip() for l in (ROOT / "Dockerfile").read_text().splitlines()]
    instructions = [l for l in lines if l and not l.startswith("#")]
    assert "USER appuser" in instructions
    assert any(l.startswith("COPY requirements.txt") for l in instructions)
    assert not any("requirements-dev" in l for l in instructions)


def test_dockerignore_keeps_secrets_and_tests_out_of_the_image():
    lines = {l.strip() for l in (ROOT / ".dockerignore").read_text().splitlines()}
    assert {".env", ".git", "tests"} <= lines


def test_runtime_requirements_exclude_dev_tools():
    runtime = (ROOT / "requirements.txt").read_text().lower()
    assert "pytest" not in runtime and "pyyaml" not in runtime
    dev = (ROOT / "requirements-dev.txt").read_text().lower()
    assert "-r requirements.txt" in dev and "pytest" in dev