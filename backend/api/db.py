import os
from collections.abc import Generator

import pymysql
from pymysql.cursors import DictCursor


def connect_db():
    return pymysql.connect(
        host=os.getenv('MARIADB_HOST', '127.0.0.1'),
        port=int(os.getenv('MARIADB_PORT', '3306')),
        database=os.getenv('MARIADB_DATABASE', 'kervion'),
        user=os.getenv('MARIADB_USER'),
        password=os.getenv('MARIADB_PASSWORD'),
        charset='utf8mb4',
        autocommit=False,
        cursorclass=DictCursor,
        connect_timeout=5,
    )


def get_db() -> Generator:
    conn = connect_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
