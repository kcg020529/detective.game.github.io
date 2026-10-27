"""Apply the repository's MariaDB schemas and migrations in filename order."""

import re
import sys
from pathlib import Path

from backend.api.db import connect_db

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / 'database' / 'schemas' / 'mariadb'
MIGRATION_DIR = ROOT / 'database' / 'migrations' / 'mariadb'
CREATE_TABLE = re.compile(r'\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?', re.IGNORECASE)


def split_sql(source):
    statements = []
    current = []
    quote = None
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ''
        if quote:
            current.append(char)
            if char == '\\' and following:
                current.append(following)
                index += 2
                continue
            if char == quote:
                if following == quote:
                    current.append(following)
                    index += 2
                    continue
                quote = None
        elif char in ("'", '"', '`'):
            quote = char
            current.append(char)
        elif char == '/' and following == '*':
            end = source.find('*/', index + 2)
            if end < 0:
                raise ValueError('Unclosed SQL block comment')
            current.append(' ')
            index = end + 2
            continue
        elif char == '#' or (char == '-' and following == '-' and
                             (index + 2 == len(source) or source[index + 2].isspace())):
            end = source.find('\n', index)
            if end < 0:
                break
            current.append('\n')
            index = end + 1
            continue
        elif char == ';':
            statement = ''.join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    statement = ''.join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def existing_tables(cursor):
    cursor.execute('SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()')
    return {row['table_name'] for row in cursor.fetchall()}


def record_applied(cursor, filename):
    cursor.execute('INSERT INTO schema_migrations (filename) VALUES (%s)', (filename,))


def apply_file(connection, path, *, schema, tables):
    filename = path.name
    with connection.cursor() as cursor:
        cursor.execute('SELECT filename FROM schema_migrations WHERE filename = %s', (filename,))
        if cursor.fetchone():
            return 'skipped'

        source = path.read_text(encoding='utf-8')
        table_names = CREATE_TABLE.findall(source) if schema else []
        if schema and table_names and set(table_names) <= tables:
            record_applied(cursor, filename)
            connection.commit()
            return 'baselined'

        try:
            for statement in split_sql(source):
                cursor.execute(statement)
            record_applied(cursor, filename)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if schema:
        tables.update(table_names)
    return 'applied'


def migrate(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            'CREATE TABLE IF NOT EXISTS schema_migrations ('
            'filename VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY, '
            'applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4')
        connection.commit()
        tables = existing_tables(cursor)

    files = [(path, True) for path in sorted(SCHEMA_DIR.glob('*.sql'))]
    files += [(path, False) for path in sorted(MIGRATION_DIR.glob('*.sql'))]
    if not files:
        raise RuntimeError('No schema or migration SQL files found')
    for path, schema in files:
        status = apply_file(connection, path, schema=schema, tables=tables)
        print(f'{status.upper()} {path.name}')


def main():
    connection = connect_db()
    try:
        migrate(connection)
    except Exception as exc:
        print(f'Migration failed and was not recorded: {exc}', file=sys.stderr)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
