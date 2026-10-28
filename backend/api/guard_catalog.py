import time

_CACHE = {}
TTL_SECONDS = 300


def invalidate(dataset=None):
    if dataset is None:
        _CACHE.clear()
    else:
        _CACHE.pop(dataset, None)


def load_catalog(conn, dataset, *, now=None):
    now = time.monotonic() if now is None else now
    cached = _CACHE.get(dataset)
    if cached is not None and now - cached[0] < TTL_SECONDS:
        return [dict(record) for record in cached[1]]
    with conn.cursor() as cursor:
        cursor.execute('SELECT record_id, record_type, day, test_id, summary, content '
                       'FROM game_records WHERE dataset = %s ORDER BY record_id', (dataset,))
        records = [dict(row) for row in cursor.fetchall()]
    _CACHE[dataset] = (now, records)
    return [dict(record) for record in records]
