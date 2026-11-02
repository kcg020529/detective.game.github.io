"""Grant the website administrator capability to an existing account.

Usage (from repository root): python -m infrastructure.docker.grant_site_admin symin123
Run only after applying 015_site_admins.sql. This does not change game roles.
"""

import argparse

from backend.api.db import connect_db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="existing website login ID")
    args = parser.parse_args()
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (args.username,))
            row = cursor.fetchone()
            if row is None:
                print("Account not found; no administrator grant was made.")
                return 1
            cursor.execute(
                "INSERT IGNORE INTO site_admins (user_id) VALUES (%s)",
                (row["user_id"],),
            )
            print(f"Administrator grant ready for {args.username} (user_id={row['user_id']}).")
        conn.commit()
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
