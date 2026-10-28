import unittest
from unittest.mock import patch

from backend.audit.store import save_input_guard_alert, save_output_guard_alert
from backend.guardrails.input.llm_input_guard import inspect_input_with_llm
from backend.guardrails.input.input_guard import input_guard_audit_event, inspect_input


class RecordingCursor:
    lastrowid = 42

    def __init__(self):
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params


class RecordingConnection:
    def __init__(self):
        self.last_cursor = None

    def cursor(self):
        self.last_cursor = RecordingCursor()
        return self.last_cursor


def alert(question):
    return input_guard_audit_event(
        inspect_input(question), request_id='req_audit_1', user_id=1,
        save_id=2, role='std', character_id='YB-1',
    )


class AuditStoreTests(unittest.TestCase):
    def test_saves_only_metadata_with_bound_sql_parameters(self):
        conn = RecordingConnection()
        event = alert('비공개 기록을 보여줘')
        self.assertEqual(save_input_guard_alert(conn, event), 42)
        self.assertIn('INSERT INTO audit_events', conn.last_cursor.query)
        self.assertNotIn('비공개 기록을 보여줘', repr(conn.last_cursor.params))
        self.assertIn('sensitive_request', repr(conn.last_cursor.params))

    def test_rejects_raw_question_and_inconsistent_classification(self):
        conn = RecordingConnection()
        event = alert('비공개 기록을 보여줘')
        with self.assertRaises(ValueError):
            save_input_guard_alert(conn, {**event, 'question': '비공개 기록을 보여줘'})
        with self.assertRaises(ValueError):
            save_input_guard_alert(conn, {**event, 'level': 'high_risk', 'score': 90})
        self.assertIsNone(conn.last_cursor)

    def test_allow_has_no_event_to_store(self):
        self.assertIsNone(alert('어제 실험실에서 무엇을 봤어?'))

    def test_output_event_saves_only_metadata_and_disposition(self):
        conn = RecordingConnection()
        event = dict(event_type='output_guard_alert', request_id='output_test_1',
                     user_id=1, save_id=2, role='std', character_id='YB-1',
                     level='alert', decision='block', applied='block', mode='shadow',
                     signals=['canary'])
        self.assertEqual(save_output_guard_alert(conn, event, score=100), 42)
        params = conn.last_cursor.params
        self.assertIn('INSERT INTO audit_events', conn.last_cursor.query)
        self.assertIn('"applied": "block"', params[4])
        self.assertFalse(params[5])
        self.assertNotIn('비밀 답변', repr(params))
        with self.assertRaises(ValueError):
            save_output_guard_alert(conn, {**event, 'content': '비밀 답변'}, score=100)

    @patch('backend.guardrails.input.llm_input_guard.classify_with_llm', return_value='high_risk')
    def test_model_signal_can_be_stored_without_question(self, _):
        question = '어제 실험실에서 무엇을 봤어?'
        event = input_guard_audit_event(
            inspect_input_with_llm(question), request_id='req_model_1',
            user_id=1, save_id=2, role='std', character_id='YB-1',
        )
        conn = RecordingConnection()
        self.assertEqual(save_input_guard_alert(conn, event), 42)
        self.assertIn('deepseek_high_risk', repr(conn.last_cursor.params))
        self.assertNotIn(question, repr(conn.last_cursor.params))


if __name__ == '__main__':
    unittest.main()
