"""The integration fixtures empty every table, so they must refuse non-test databases.

Unit test: needs no database, only the guard function.
"""
import pytest

from tests.integration.conftest import _assert_test_database


@pytest.mark.parametrize("url", [
    "postgresql://u:p@localhost:5433/portfolio_analytics_test",
    "postgresql://u:p@localhost/anything_test",
])
def test_test_databases_are_allowed(url):
    _assert_test_database(url)


@pytest.mark.parametrize("url", [
    "postgresql://u:p@localhost:5432/portfolio_analytics",
    "postgresql://u:p@localhost/postgres",
    "postgresql://u:p@localhost/test_data_prod",
    "postgresql://u:p@localhost",
])
def test_other_databases_are_refused(url):
    with pytest.raises(RuntimeError, match="_test"):
        _assert_test_database(url)
