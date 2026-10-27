import unittest
from unittest.mock import patch

from backend.audit.input_guard_flow import inspect_and_record_input
from backend.guardrails.input.input_guard import InputGuardResult


class InputGuardFlowTests(unittest.TestCase):
    @patch('backend.audit.input_guard_flow.save_input_guard_alert')
    @patch('backend.audit.input_guard_flow.inspect_input_with_llm')
    def test_warning_records_metadata_and_continues(self, classify, save):
        classify.return_value = InputGuardResult('warn', 50, ('sensitive_request',))
        conn = object()
        result = inspect_and_record_input(
            conn, '비공개 기록을 보여줘', request_id='req_flow_1',
            user_id=3, save_id=4, role='std', character_id='YB-1',
        )
        self.assertTrue(result.continue_processing)
        event = save.call_args.args[1]
        self.assertIs(save.call_args.args[0], conn)
        self.assertEqual(event['level'], 'warn')
        self.assertEqual((event['user_id'], event['save_id'], event['role']), (3, 4, 'std'))
        self.assertNotIn('비공개 기록을 보여줘', repr(event))

    @patch('backend.audit.input_guard_flow.save_input_guard_alert')
    @patch('backend.audit.input_guard_flow.inspect_input_with_llm')
    def test_allow_continues_without_audit_row(self, classify, save):
        classify.return_value = InputGuardResult('allow', 0, ())
        result = inspect_and_record_input(
            object(), '어제 뭘 봤어?', request_id='req_flow_2',
            user_id=3, save_id=4, role='std', character_id='YB-1',
        )
        self.assertEqual(result.level, 'allow')
        self.assertTrue(result.continue_processing)
        save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
