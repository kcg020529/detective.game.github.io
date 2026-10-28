from backend.api import guard_catalog


class Connection:
    def __init__(self): self.calls = 0
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params):
        self.calls += 1
        assert query == ('SELECT record_id, record_type, day, test_id, summary, content '
                         'FROM game_records WHERE dataset = %s ORDER BY record_id')
        assert params == ('test-data',)
    def fetchall(self):
        return [dict(record_id='r1', record_type='Action', day=1, test_id=1,
                     summary='요약 문자열', content='본문 문자열')]


def test_catalog_cache_hit_expiry_and_invalidation():
    guard_catalog.invalidate()
    conn = Connection()
    first = guard_catalog.load_catalog(conn, 'test-data', now=10)
    second = guard_catalog.load_catalog(conn, 'test-data', now=309.9)
    assert first == second and conn.calls == 1
    assert guard_catalog.load_catalog(conn, 'test-data', now=310) == first
    assert conn.calls == 2
    guard_catalog.invalidate('test-data')
    guard_catalog.load_catalog(conn, 'test-data', now=311)
    assert conn.calls == 3
