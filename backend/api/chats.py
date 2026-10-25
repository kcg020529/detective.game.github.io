import json
import logging
import secrets

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from pymysql.connections import Connection

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError
from backend.api.saves import _date, _owned_save
from backend.character_ai.service import ChatReply, ReplyGenerator, get_reply_generator
from backend.guardrails.input_guard import input_guard_audit_event, inspect_input

router = APIRouter()
logger = logging.getLogger(__name__)


class SendChat(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    client_request_id: str = Field(pattern=r'^[\x21-\x7E]{1,64}$')


def _logged_chat(cursor, save_id: int, request_id: str, ai_id: str, question: str, *, lock: bool = False):
    cursor.execute(
        'SELECT endpoint, response_json FROM request_log '
        'WHERE save_id = %s AND client_request_id = %s' + (' FOR UPDATE' if lock else ''),
        (save_id, request_id),
    )
    logged = cursor.fetchone()
    if not logged:
        return None
    if logged['endpoint'] != f'chat:{ai_id}':
        raise ApiError(409, 'STATE_CONFLICT', '같은 요청 ID가 다른 작업에 사용되었습니다.')
    response = logged['response_json']
    response = json.loads(response) if isinstance(response, (str, bytes, bytearray)) else response
    if response['messages'][0]['content'] != question:
        raise ApiError(409, 'STATE_CONFLICT', '같은 요청 ID에 다른 질문이 사용되었습니다.')
    return response


@router.post('/saves/{save_id}/chats/{ai_id}')
def send_chat(
    body: SendChat,
    save_id: int = Path(gt=0),
    ai_id: str = Path(pattern=r'^YB-[1-6]$'),
    conn: Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    generate_reply: ReplyGenerator = Depends(get_reply_generator),
):
    question = body.message.strip()
    if not question:
        raise ApiError(422, 'VALIDATION_ERROR', '질문을 입력해 주세요.')

    with conn.cursor() as cursor:
        save = _owned_save(cursor, user_id, save_id)
        previous = _logged_chat(cursor, save_id, body.client_request_id, ai_id, question)
        if previous is not None:
            return previous

    request_id = f'req_{secrets.token_hex(8)}'
    guard = inspect_input(question)
    alert = input_guard_audit_event(
        guard, request_id=request_id, user_id=user_id, save_id=save_id,
        role=save['role'], character_id=ai_id,
    )
    if alert is not None:
        logger.warning('input_guard_alert %s', json.dumps(alert, ensure_ascii=False))

    # The generator must receive only policy-approved context when D/F/E are
    # connected. This first interface passes no database records to it.
    reply = generate_reply(ai_id=ai_id, question=question, role=save['role'], day=int(save['day']))
    if not isinstance(reply, ChatReply) or not reply.content.strip():
        raise ApiError(503, 'SERVICE_UNAVAILABLE', 'AI 응답을 만들지 못했습니다.')

    with conn.cursor() as cursor:
        current = _owned_save(cursor, user_id, save_id, lock=True)
        previous = _logged_chat(cursor, save_id, body.client_request_id, ai_id, question, lock=True)
        if previous is not None:
            return previous
        if current['day'] != save['day'] or current['role'] != save['role']:
            raise ApiError(409, 'STATE_CONFLICT', '게임 상태가 바뀌었습니다. 다시 질문해 주세요.')
        cursor.execute(
            'INSERT INTO chat_messages (save_id, ai_id, sender, content, response_type) '
            'VALUES (%s, %s, %s, %s, NULL)',
            (save_id, ai_id, 'user', question),
        )
        user_message_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO chat_messages (save_id, ai_id, sender, content, response_type) '
            'VALUES (%s, %s, %s, %s, %s)',
            (save_id, ai_id, 'ai', reply.content.strip(), reply.response_type),
        )
        ai_message_id = cursor.lastrowid
        cursor.execute(
            'SELECT message_id, ai_id, sender, content, response_type, created_at '
            'FROM chat_messages WHERE message_id IN (%s, %s) ORDER BY message_id',
            (user_message_id, ai_message_id),
        )
        messages = [
            {**row, 'message_id': int(row['message_id']), 'created_at': _date(row['created_at'])}
            for row in cursor.fetchall()
        ]
        response = {
            'request_id': request_id,
            'messages': messages,
            'game_state': {'current_day': int(current['day'])},
        }
        cursor.execute(
            'INSERT INTO request_log (save_id, client_request_id, endpoint, response_json) '
            'VALUES (%s, %s, %s, %s)',
            (save_id, body.client_request_id, f'chat:{ai_id}',
             json.dumps(response, ensure_ascii=False, separators=(',', ':'))),
        )
        cursor.execute(
            'UPDATE saves SET last_played_at = NOW() WHERE save_id = %s AND user_id = %s',
            (save_id, user_id),
        )
        return response


@router.get('/saves/{save_id}/chats/{ai_id}')
def list_chats(
    save_id: int = Path(gt=0),
    ai_id: str = Path(pattern=r'^YB-[1-6]$'),
    limit: int = Query(default=20, ge=1, le=50),
    before: int | None = Query(default=None, gt=0),
    conn: Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
):
    with conn.cursor() as cursor:
        _owned_save(cursor, user_id, save_id)
        query = (
            'SELECT message_id, ai_id, sender, content, response_type, created_at '
            'FROM chat_messages WHERE save_id = %s AND ai_id = %s'
        )
        params = [save_id, ai_id]
        if before is not None:
            query += ' AND message_id < %s'
            params.append(before)
        query += ' ORDER BY message_id DESC LIMIT %s'
        params.append(limit + 1)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        has_more = len(rows) > limit
        messages = [
            {
                'message_id': int(row['message_id']),
                'ai_id': row['ai_id'],
                'sender': row['sender'],
                'content': row['content'],
                'response_type': row['response_type'],
                'created_at': _date(row['created_at']),
            }
            for row in reversed(rows[:limit])
        ]
        return {'messages': messages, 'has_more': has_more}
