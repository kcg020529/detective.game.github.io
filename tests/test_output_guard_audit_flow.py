from types import SimpleNamespace

from backend.audit.output_guard_flow import record_output_guard_result


class Connection:
    def __init__(self):
        self.params = None
        self.lastrowid = 9
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        assert 'INSERT INTO audit_events' in query
        self.params = params

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


CTX = SimpleNamespace(user_id=1, save_id=2, role='std', character_id='YB-1')


def test_output_event_uses_chat_transaction_without_answer_text():
    conn = Connection()
    result = dict(event='alert', decision='block', applied='block', mode='shadow',
                  reasons=['canary'], gray=[], checks=[{'name': 'canary', 'score': 1.0}],
                  text='안전한 안내', raw_answer='비밀 답변')
    assert record_output_guard_result(result, context=CTX, conn=conn) == 9
    assert conn.commits == 0 and not conn.closed
    assert conn.params[3] == 100
    assert '비밀 답변' not in repr(conn.params)
    assert '안전한 안내' not in repr(conn.params)


def test_clean_output_does_not_write_audit_event():
    result = dict(event='none')
    conn = Connection()
    assert record_output_guard_result(result, context=CTX, conn=conn) is None
    assert conn.params is None
