"""Adapt the reviewed G-2 checker to the chat pipeline response contract."""
from backend.guardrails.output import OutputGuard, load_config

RESPONSE_TYPES = frozenset({'normal', 'partial', 'restricted', 'unknown'})
LEAK_REASONS = frozenset({'canary', 'api_key', 'pii', 'context_leak', 'prompt_leak'})


class OutputGuardRejected(ValueError):
    """G-2 recorded an event, then rejected an unsafe or unmapped answer."""


def check_output(*, draft, question, context, records, conn=None, audit_sink=None):
    """Return only the checked final answer; raise for an invalid draft/result.

    RAG supplies only authorized records. Since that is not the full record
    catalog, the unauthorized-context comparison is intentionally skipped.
    """
    if (not isinstance(draft, dict) or set(draft) != {'content', 'response_type'}
            or not isinstance(draft['content'], str)
            or draft['response_type'] not in RESPONSE_TYPES):
        raise ValueError('Invalid character draft contract')
    if not isinstance(question, str) or not question.strip():
        raise ValueError('Invalid question contract')
    if not isinstance(records, list):
        raise ValueError('Invalid records contract')
    guard = OutputGuard(load_config(), records=records)
    result = guard.check(
        draft['content'], user_input=question, role=context.role, day=context.day,
        target_ai=context.character_id, allowed_context_ids=None)
    if (not isinstance(result, dict) or result.get('applied') not in ('allow', 'mask', 'block')
            or not isinstance(result.get('text'), str)
            or not isinstance(result.get('reasons'), list)):
        raise ValueError('Invalid Output Guard result')
    if audit_sink is not None:
        audit_sink(result, context=context, conn=conn)
    if not result['text'].strip():
        raise OutputGuardRejected('Empty Output Guard result')
    if result['applied'] == 'allow':
        response_type = draft['response_type']
    elif result['applied'] == 'mask' and result.get('decision') == 'mask':
        response_type = 'partial'
    elif (result['applied'] == 'block' and result.get('decision') == 'block'
          and result['reasons'] and result['reasons'][0] in LEAK_REASONS
          and 'broken' not in result['reasons']):
        response_type = 'restricted'
    else:
        # Broken output and quality blocks have no agreed response type.
        raise OutputGuardRejected('Output Guard result cannot be mapped safely')
    return {'content': result['text'], 'response_type': response_type}
