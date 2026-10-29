"""The engine must name its driver, so it does not depend on SQLAlchemy's default.

SQLAlchemy 2.1 changed the default for a bare postgresql:// URL from psycopg2 to
psycopg (v3); this project installs psycopg2-binary only.
"""
import pytest
from sqlalchemy.engine import make_url

from src.db import engine, with_explicit_driver


@pytest.mark.parametrize("url", [
    "postgresql://u:p@localhost:5432/db",
    "postgres://u:p@localhost:5432/db",
])
def test_bare_postgres_urls_get_the_psycopg2_driver(url):
    out = make_url(with_explicit_driver(url))
    assert out.drivername == "postgresql+psycopg2"
    assert (out.username, out.password, out.host, out.port, out.database) == ("u", "p", "localhost", 5432, "db")


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://u:p@localhost/db",
    "postgresql+psycopg://u:p@localhost/db",
])
def test_an_explicit_driver_is_left_alone(url):
    assert with_explicit_driver(url) == url


def test_special_characters_in_the_password_survive():
    out = make_url(with_explicit_driver("postgresql://u:p%40ss%2Fword@localhost/db"))
    assert out.password == "p@ss/word"


def test_the_application_engine_uses_psycopg2():
    assert engine.dialect.driver == "psycopg2"
