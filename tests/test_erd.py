"""Keeps the ERD in step with sql/schema.sql and the README."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "sql" / "schema.sql").read_text()
ERD = (ROOT / "docs" / "erd.mmd").read_text()
README = (ROOT / "README.md").read_text().replace("\r\n", "\n")


def _schema_tables() -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA))


def _erd_tables() -> set[str]:
    return set(re.findall(r"^    (\w+) \{", ERD, flags=re.MULTILINE))


def test_erd_has_every_schema_table():
    assert _schema_tables() == _erd_tables()


def test_erd_has_every_schema_column():
    for table in _schema_tables():
        ddl = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", SCHEMA, re.S).group(1)
        cols = set(re.findall(r"^\s{4}(\w+)\s+[A-Z]", ddl, flags=re.MULTILINE)) - {"PRIMARY", "CHECK", "UNIQUE"}
        alters = set(re.findall(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS (\w+)", SCHEMA))
        block = re.search(rf"^    {table} \{{(.*?)^    \}}", ERD, re.S | re.M).group(1)
        erd_cols = set(re.findall(r"^\s+\w+ (\w+)", block, flags=re.MULTILINE))
        assert cols | alters == erd_cols, table


def test_readme_embeds_the_current_erd():
    assert ERD.strip() in README