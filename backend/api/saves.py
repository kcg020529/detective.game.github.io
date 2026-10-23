import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from pymysql.connections import Connection
from pymysql.err import IntegrityError

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError

router = APIRouter()


class CreateSave(BaseModel):
    slot_no: int = Field(ge=1, le=3)
    role: Literal['prof', 'grad', 'std']
    overwrite: bool = False


class SaveMemo(BaseModel):
    memo: str = Field(max_length=5000)


class AdvanceDay(BaseModel):
    client_request_id: str = Field(pattern=r'^[\x21-\x7E]{1,64}$')


def _date(value: datetime) -> str:
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _save(row: dict) -> dict:
    return {
        'save_id': int(row['save_id']),
        'slot_no': int(row['slot_no']),
        'role': row['role'],
        'day': int(row['day']),
        'created_at': _date(row['created_at']),
        'last_played_at': _date(row['last_played_at']),
    }


def _owned_save(cursor, user_id: int, save_id: int, lock: bool = False):
    query = (
        'SELECT save_id, slot_no, role, day, created_at, last_played_at '
        'FROM saves WHERE save_id = %s AND user_id = %s'
    )
    if lock:
        query += ' FOR UPDATE'
    cursor.execute(query, (save_id, user_id))
    row = cursor.fetchone()
    if not row:
        raise ApiError(404, 'NOT_FOUND', '기록을 찾을 수 없습니다.')
    return row


def _game_state(cursor, row: dict) -> dict:
    cursor.execute('SELECT memo FROM save_memos WHERE save_id = %s', (row['save_id'],))
    memo = cursor.fetchone()
    return {
        **_save(row),
        'current_day': int(row['day']),
        'memo': memo['memo'] if memo else '',
        'accusation': None,
    }


@router.get('/saves')
def list_saves(conn: Connection = Depends(get_db), user_id: int = Depends(current_user_id)):
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT save_id, slot_no, role, day, created_at, last_played_at '
            'FROM saves WHERE user_id = %s ORDER BY slot_no',
            (user_id,),
        )
        return {'saves': [_save(row) for row in cursor.fetchall()]}


@router.post('/saves', status_code=201)
def create_save(body: CreateSave, conn: Connection = Depends(get_db), user_id: int = Depends(current_user_id)):
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT save_id FROM saves WHERE user_id = %s AND slot_no = %s FOR UPDATE',
            (user_id, body.slot_no),
        )
        old = cursor.fetchone()
        if old and not body.overwrite:
            raise ApiError(409, 'STATE_CONFLICT', '이미 기록이 있는 슬롯입니다.')
        if old:
            cursor.execute('DELETE FROM saves WHERE save_id = %s AND user_id = %s', (old['save_id'], user_id))
        try:
            cursor.execute(
                'INSERT INTO saves (user_id, slot_no, role, day, created_at, last_played_at) '
                'VALUES (%s, %s, %s, 1, NOW(), NOW())',
                (user_id, body.slot_no, body.role),
            )
        except IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:
                raise ApiError(409, 'STATE_CONFLICT', '이미 기록이 있는 슬롯입니다.') from exc
            raise
        save_id = cursor.lastrowid
        cursor.execute(
            'SELECT save_id, slot_no, role, day, created_at, last_played_at '
            'FROM saves WHERE save_id = %s AND user_id = %s',
            (save_id, user_id),
        )
        return _save(cursor.fetchone())


@router.get('/saves/{save_id}')
def get_save(save_id: int = Path(gt=0), conn: Connection = Depends(get_db), user_id: int = Depends(current_user_id)):
    with conn.cursor() as cursor:
        row = _owned_save(cursor, user_id, save_id)
        cursor.execute('UPDATE saves SET last_played_at = NOW() WHERE save_id = %s AND user_id = %s', (save_id, user_id))
        cursor.execute(
            'SELECT save_id, slot_no, role, day, created_at, last_played_at '
            'FROM saves WHERE save_id = %s AND user_id = %s',
            (save_id, user_id),
        )
        return _game_state(cursor, cursor.fetchone())


@router.put('/saves/{save_id}/memo')
def put_memo(body: SaveMemo, save_id: int = Path(gt=0), conn: Connection = Depends(get_db), user_id: int = Depends(current_user_id)):
    with conn.cursor() as cursor:
        _owned_save(cursor, user_id, save_id, lock=True)
        cursor.execute(
            'INSERT INTO save_memos (save_id, memo) VALUES (%s, %s) '
            'ON DUPLICATE KEY UPDATE memo = VALUES(memo)',
            (save_id, body.memo),
        )
        cursor.execute('UPDATE saves SET last_played_at = NOW() WHERE save_id = %s AND user_id = %s', (save_id, user_id))
        cursor.execute('SELECT memo, updated_at FROM save_memos WHERE save_id = %s', (save_id,))
        row = cursor.fetchone()
        return {'memo': row['memo'], 'updated_at': _date(row['updated_at'])}


@router.post('/saves/{save_id}/advance-day')
def advance_day(body: AdvanceDay, save_id: int = Path(gt=0), conn: Connection = Depends(get_db), user_id: int = Depends(current_user_id)):
    with conn.cursor() as cursor:
        row = _owned_save(cursor, user_id, save_id, lock=True)
        cursor.execute(
            'SELECT endpoint, response_json FROM request_log WHERE save_id = %s AND client_request_id = %s',
            (save_id, body.client_request_id),
        )
        logged = cursor.fetchone()
        if logged:
            cursor.execute('UPDATE saves SET last_played_at = NOW() WHERE save_id = %s AND user_id = %s', (save_id, user_id))
            response = logged['response_json']
            return json.loads(response) if isinstance(response, (str, bytes, bytearray)) else response
        if row['day'] >= 6:
            raise ApiError(409, 'STATE_CONFLICT', '마지막 Day입니다.')
        cursor.execute('UPDATE saves SET day = day + 1, last_played_at = NOW() WHERE save_id = %s AND user_id = %s', (save_id, user_id))
        cursor.execute(
            'SELECT save_id, slot_no, role, day, created_at, last_played_at '
            'FROM saves WHERE save_id = %s AND user_id = %s',
            (save_id, user_id),
        )
        response = {'game_state': _game_state(cursor, cursor.fetchone())}
        cursor.execute(
            'INSERT INTO request_log (save_id, client_request_id, endpoint, response_json) '
            'VALUES (%s, %s, %s, %s)',
            (save_id, body.client_request_id, 'advance-day', json.dumps(response, ensure_ascii=False, separators=(',', ':'))),
        )
        return response
