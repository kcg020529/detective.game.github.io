"""Create a MariaDB account that can read only H audit events.

Run from the repository root after MariaDB and 012_audit_events.sql are ready.
Credentials are read from infrastructure/docker/.env and are never printed.
"""

import argparse
from pathlib import Path
import re

import pymysql


DEFAULT_ENV = Path(__file__).with_name(".env")
IDENTIFIER = re.compile(r"[A-Za-z0-9_]+\Z")


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def setup_reader(values: dict[str, str]) -> None:
    database = values.get("MARIADB_DATABASE", "kervion")
    username = values.get("GRAFANA_DB_USER", "grafana_reader")
    password = values.get("GRAFANA_DB_PASSWORD")
    root_password = values.get("MARIADB_ROOT_PASSWORD")
    if not all((password, root_password)):
        raise ValueError("Set GRAFANA_DB_PASSWORD and MARIADB_ROOT_PASSWORD in Docker .env")
    if not IDENTIFIER.fullmatch(database) or not IDENTIFIER.fullmatch(username):
        raise ValueError("Database and reader names must contain only letters, digits, or underscore")

    conn = pymysql.connect(
        host="127.0.0.1",
        port=int(values.get("MARIADB_PORT", "3306")),
        user="root",
        password=root_password,
        database=database,
        connect_timeout=5,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = 'audit_events'",
                (database,),
            )
            if cursor.fetchone()[0] != 1:
                raise ValueError("audit_events table is missing; apply 012_audit_events.sql first")
            account = f"'{username}'@'%'"
            parameterized_account = account.replace("%", "%%")
            cursor.execute(f"CREATE USER IF NOT EXISTS {parameterized_account} IDENTIFIED BY %s", (password,))
            cursor.execute(f"ALTER USER {parameterized_account} IDENTIFIED BY %s", (password,))
            cursor.execute(f"GRANT SELECT ON `{database}`.`audit_events` TO {account}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    setup_reader(read_env(args.env_file))
    print("Grafana audit reader is ready (SELECT on audit_events only).")
