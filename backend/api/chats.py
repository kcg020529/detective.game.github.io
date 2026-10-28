import hashlib
import json
import os
import secrets

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymysql.connections import Connection

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.saves import _date, _owned_save, _game_state
from backend.api.errors import ApiError
from backend.api.chat_pipeline import ChatPipeline
from backend.audit.input_guard_flow import inspect_and_record_input
from backend.policy.engine import PolicyContext
from backend.api.switches import chat_dataset, input_guard_mode

router = APIRouter()


class SendChat(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    message: str = Field(min_length=1, max_length=2000)
    client_request_id: str = Field(pattern=r'^[\x21-\x7E]{1,64}$')

    @field_validator('message')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('empty message')
        return value


@router.post('/saves/{save_id}/chats/{ai_id}')
def send_chat(body: SendChat, request: Request,
              save_id: int = Path(gt=0), ai_id: str = Path(pattern=r'^YB-[1-6]$'),
              conn: Connection = Depends(get_db, scope='function'),
              user_id: int = Depends(current_user_id)):
    # Audit is a separate committed phase: downstream AI failures must not erase alerts.
    with conn.cursor() as cursor:
        row = _owned_save(cursor, user_id, save_id)
    if input_guard_mode() == 'on':
        inspect_and_record_input(
            conn, body.message, request_id='chat_' + secrets.token_hex(16),
            user_id=user_id, save_id=save_id, role=row['role'], character_id=ai_id,
            use_llm=os.getenv('KERVION_INPUT_GUARD_LLM') == '1')
    conn.commit()
    with conn.cursor() as cursor:
        row = _owned_save(cursor, user_id, save_id, lock=True)
        fingerprint = hashlib.sha256(body.message.encode('utf-8')).hexdigest()
        endpoint = 'chat:' + ai_id
        cursor.execute('SELECT endpoint, response_json FROM request_log '
                       'WHERE save_id = %s AND client_request_id = %s',
                       (save_id, body.client_request_id))
        logged = cursor.fetchone()
        if logged:
            data = logged['response_json']
            data = json.loads(data) if isinstance(data, (str, bytes, bytearray)) else data
            if (logged['endpoint'] != endpoint or data.get('message_hash') != fingerprint):
                raise ApiError(409, 'STATE_CONFLICT', '다른 요청에 사용한 요청 ID입니다.')
            return data['response']
        cursor.execute('SELECT sender, content FROM chat_messages '
                       'WHERE save_id = %s AND ai_id = %s ORDER BY message_id DESC LIMIT 12',
                       (save_id, ai_id))
        history = [dict(save_id=save_id, character_id=ai_id, **turn)
                   for turn in reversed(cursor.fetchall())]
        while history and sum(len(turn['content']) for turn in history) > 24000:
            history.pop(0)
    context = PolicyContext(user_id, save_id, user_id, row['role'], int(row['day']),
                            ai_id, chat_dataset())
    pipeline = getattr(request.app.state, 'chat_pipeline', None) or ChatPipeline()
    answer = pipeline.reply(conn=conn, question=body.message, context=context, history=history)
    with conn.cursor() as cursor:
        ids = []
        for sender, content, response_type in (
                ('user', body.message, None),
                ('ai', answer['content'], answer['response_type'])):
            cursor.execute('INSERT INTO chat_messages '
                           '(save_id, ai_id, sender, content, response_type) VALUES (%s,%s,%s,%s,%s)',
                           (save_id, ai_id, sender, content, response_type))
            ids.append(cursor.lastrowid)
        cursor.execute('SELECT message_id, ai_id, sender, content, response_type, created_at '
                       'FROM chat_messages WHERE save_id = %s AND message_id IN (%s,%s) '
                       'ORDER BY message_id', (save_id, *ids))
        messages = [{**item, 'message_id': int(item['message_id']),
                     'created_at': _date(item['created_at'])} for item in cursor.fetchall()]
        cursor.execute('UPDATE saves SET last_played_at = NOW() '
                       'WHERE save_id = %s AND user_id = %s', (save_id, user_id))
        row = _owned_save(cursor, user_id, save_id)
        response = dict(messages=messages, game_state=_game_state(cursor, row))
        cursor.execute('INSERT INTO request_log '
                       '(save_id, client_request_id, endpoint, response_json) VALUES (%s,%s,%s,%s)',
                       (save_id, body.client_request_id, endpoint,
                        json.dumps(dict(message_hash=fingerprint, response=response), ensure_ascii=False)))
    return response


@router.get('/saves/{save_id}/chats/{ai_id}')
def list_chats(
    save_id: int = Path(gt=0),
    ai_id: str = Path(pattern=r'^YB-[1-6]$'),
    limit: int = Query(default=20, ge=1, le=50),
    before: int | None = Query(default=None, gt=0),
    conn: Connection = Depends(get_db, scope='function'),
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
