"""MariaDB connection used by the first account and Save endpoints."""

from contextlib import contextmanager
import os

import pymysql


@contextmanager
def transaction():
    password = os.getenv("KERVION_DB_PASSWORD") or os.getenv("MARIADB_PASSWORD")
    if not password:
        raise pymysql.OperationalError(0, "KERVION_DB_PASSWORD is not configured")

    connection = pymysql.connect(
        host=os.getenv("KERVION_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("KERVION_DB_PORT", os.getenv("MARIADB_PORT", "3306"))),
        user=os.getenv("KERVION_DB_USER", os.getenv("MARIADB_USER", "kervion")),
        password=password,
        database=os.getenv("KERVION_DB_NAME", os.getenv("MARIADB_DATABASE", "kervion")),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
        autocommit=False,
    )
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
