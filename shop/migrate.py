"""Run once before starting API/worker; safe to rerun on an existing database."""
from pathlib import Path

from shop.store import connect


def main() -> None:
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(741921)")
        db.execute("CREATE TABLE IF NOT EXISTS schema_versions (version integer PRIMARY KEY)")
        if db.execute("SELECT 1 FROM schema_versions WHERE version = 1").fetchone() is None:
            db.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            db.execute("INSERT INTO schema_versions VALUES (1)")


if __name__ == "__main__":
    main()
