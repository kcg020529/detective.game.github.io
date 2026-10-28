"""Adapt the reviewed G-2 checker to the chat pipeline response contract."""
import logging
import os

from backend.guardrails.output import OutputGuard, load_config
from backend.guardrails.output.prompt_check import sentences_from_text

logger = logging.getLogger(__name__)
_PROMPT_SENTENCES = {}

RESPONSE_TYPES = frozenset({'normal', 'partial', 'restricted', 'unknown'})
LEAK_REASONS = frozenset({'canary', 'api_key', 'pii', 'context_leak', 'prompt_leak'})


class OutputGuardRejected(ValueError):
    """G-2 recorded an event, then rejected an unsafe or unmapped answer."""


def check_output(*, draft, question, context, records, conn=None, audit_sink=None, render=None):
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
    cfg = load_config()
    cfg.setdefault('secrets', {}).setdefault('api_keys', []).extend(
        key for key in (os.getenv('DEEPSEEK_API_KEY'), os.getenv('DEEPSEEK_PLANNER_API_KEY')) if key)
    mode = os.getenv('KERVION_OUTPUT_GUARD_MODE')
    if mode in ('enforce', 'shadow'):
        cfg['mode'] = mode
    # 설정 파일의 기본 mode는 shadow다.
    allowed_context_ids = None
    guard_records = records
    if conn is not None:
        from backend.api.guard_catalog import load_catalog

        catalog = load_catalog(conn, context.dataset)
        allowed = {record['record_id']: record for record in records}
        guard_records = []
        for catalog_record in catalog:
            record_id = catalog_record['record_id']
            if record_id not in allowed:
                guard_records.append(catalog_record)
                continue
            cut = allowed[record_id]
            guard_records.append(cut)
            withheld = {field: (catalog_record.get(field) or '')
                        if not cut.get(field) and catalog_record.get(field) else ''
                        for field in ('summary', 'content')}
            if any(withheld.values()):
                guard_records.append({'record_id': f'{record_id}#withheld', **withheld})
        allowed_context_ids = list(allowed)
    prompt_sentences = _PROMPT_SENTENCES.get(context.character_id)
    if prompt_sentences is None:
        try:
            if render is None:
                from backend.character_ai.prompt_render import render_actor_prompt

                render = render_actor_prompt
            sentences = sentences_from_text(render(context.character_id, 'answer', memory=[], history=[]))
            _PROMPT_SENTENCES[context.character_id] = sentences
            prompt_sentences = sentences
        except Exception:
            logger.warning('Could not load output guard prompt sentences')
            prompt_sentences = []
    guard = OutputGuard(cfg, records=guard_records, prompt_sentences=prompt_sentences)
    result = guard.check(
        draft['content'], user_input=question, role=context.role, day=context.day,
        target_ai=context.character_id, allowed_context_ids=allowed_context_ids)
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
