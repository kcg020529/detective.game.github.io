"""Adapt the reviewed G-2 checker to the chat pipeline response contract."""
from backend.guardrails.output import OutputGuard, load_config

RESPONSE_TYPES = frozenset({'normal', 'partial', 'restricted', 'unknown'})


def check_output(*, draft, context, records):
    """Return only the checked final answer; raise for an invalid draft/result.

    RAG supplies only authorized records. Since that is not the full record
    catalog, the unauthorized-context comparison is intentionally skipped.
    """
    if (not isinstance(draft, dict) or set(draft) != {'content', 'response_type'}
            or not isinstance(draft['content'], str)
            or draft['response_type'] not in RESPONSE_TYPES):
        raise ValueError('Invalid character draft contract')
    if not isinstance(records, list):
        raise ValueError('Invalid records contract')
    guard = OutputGuard(load_config(), records=records)
    result = guard.check(
        draft['content'], role=context.role, day=context.day,
        target_ai=context.character_id, allowed_context_ids=None)
    if (not isinstance(result, dict) or result.get('applied') not in ('allow', 'mask', 'block')
            or not isinstance(result.get('text'), str)):
        raise ValueError('Invalid Output Guard result')
    if result['applied'] != 'allow':
        raise ValueError('Output Guard response type mapping is not agreed')
    return {'content': result['text'], 'response_type': draft['response_type']}
