import logging

from backend.rag.service import Retrieval, build_memory, resolve_used

logger = logging.getLogger(__name__)

CLARIFICATIONS = {
    'AMBIGUOUS_REFERENCE': '어떤 인물이나 회차를 말씀하시는 건가요?',
    'INSUFFICIENT_CONTEXT': '조금 더 구체적으로 알려 주실 수 있나요?',
}


def make_generator(chat=None, render=None, fixed=None):
    def generator(*, question, context, history, plan, records, retrieval=None):
        nonlocal chat, render, fixed
        character_id = context.character_id
        if plan.route == 'clarify':
            # 임시: D에 clarify 모드가 생기면 바꾼다.
            return {'content': CLARIFICATIONS[plan.clarification_code], 'response_type': 'unknown'}
        if plan.route == 'out_of_scope' or (plan.route == 'retrieve' and retrieval is not None
                                             and retrieval.signal == 'no_allowed_records'):
            if fixed is None:
                from backend.character_ai.prompt_render import fixed_reply
                fixed = fixed_reply
            mode = 'off_topic' if plan.route == 'out_of_scope' else 'restricted'
            # 임시: out_of_scope 유형 확정 전에는 unknown으로 저장한다.
            return {'content': fixed(character_id, mode)['reply'],
                    'response_type': 'unknown' if mode == 'off_topic' else 'restricted'}

        memory, id_map = [], {}
        if plan.route == 'retrieve':
            if retrieval is None:
                memory, id_map = build_memory(records)
                retrieval = Retrieval(records, memory, 'ok' if records else 'no_match', id_map)
            memory, id_map = retrieval.memory, retrieval.id_map
        mode = 'unknown' if plan.route == 'retrieve' and not memory else 'answer'
        if chat is None:
            from backend.character_ai.llm_client import chat_json
            chat = chat_json
        if render is None:
            from backend.character_ai.prompt_render import render_actor_prompt
            render = render_actor_prompt
        turns = [{'speaker': '조사자' if turn['sender'] == 'user' else character_id,
                  'text': turn['content']} for turn in history[-6:]]
        prompt = render(character_id, mode, memory=memory if mode == 'answer' else [], history=turns)
        data = chat(prompt, question)['data']
        used, dropped = resolve_used(data.get('used'), id_map)
        logger.debug('memory used=%d dropped=%d', len(used), len(dropped))
        reply = data['reply']
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError('empty character reply')
        return {'content': reply, 'response_type': 'normal' if mode == 'answer' else 'unknown'}

    return generator
