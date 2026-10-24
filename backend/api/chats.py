from fastapi import APIRouter, Depends, Path, Query
from pymysql.connections import Connection

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.saves import _date, _owned_save

router = APIRouter()


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
