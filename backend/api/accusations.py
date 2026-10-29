import json
from typing import Literal

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.connections import Connection

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError
from backend.api.saves import _owned_save
from backend.api.verdict import VERDICT, read_accusation

router = APIRouter()


class SubmitAccusation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    character_id: Literal['YB-1', 'YB-2', 'YB-3', 'YB-4', 'YB-5', 'YB-6']
    client_request_id: str = Field(pattern=r'^[\x21-\x7E]{1,64}$')


@router.post('/saves/{save_id}/accusations')
def submit_accusation(body: SubmitAccusation, save_id: int = Path(gt=0),
                      conn: Connection = Depends(get_db, scope='function'),
                      user_id: int = Depends(current_user_id)):
    with conn.cursor() as cursor:
        save = _owned_save(cursor, user_id, save_id, lock=True)
        # 세션 조회가 만든 이전 스냅샷 대신 잠금 이후의 최신 제출을 확인한다.
        cursor.execute('SELECT endpoint, response_json FROM request_log '
                       'WHERE save_id = %s AND client_request_id = %s FOR UPDATE',
                       (save_id, body.client_request_id))
        logged = cursor.fetchone()
        if logged:
            data = logged['response_json']
            data = json.loads(data) if isinstance(data, (str, bytes, bytearray)) else data
            if logged['endpoint'] != 'accusation' or data.get('character_id') != body.character_id:
                raise ApiError(409, 'STATE_CONFLICT', '다른 요청에 사용한 요청 ID입니다.')
            return data['response']
        if int(save['day']) != 6:
            raise ApiError(409, 'STATE_CONFLICT', '최종 지목은 마지막 Day에만 할 수 있습니다.')
        cursor.execute('SELECT ai_id FROM accusations WHERE save_id = %s FOR UPDATE', (save_id,))
        if cursor.fetchone():
            raise ApiError(409, 'STATE_CONFLICT', '이미 최종 지목을 제출했습니다.')
        cursor.execute('INSERT INTO accusations (save_id, ai_id, is_correct) VALUES (%s, %s, %s)',
                       (save_id, body.character_id, body.character_id == VERDICT['culprit_id']))
        response = {'accusation': read_accusation(cursor, save)}
        cursor.execute('INSERT INTO request_log (save_id, client_request_id, endpoint, response_json) '
                       'VALUES (%s, %s, %s, %s)',
                       (save_id, body.client_request_id, 'accusation',
                        json.dumps(dict(character_id=body.character_id, response=response), ensure_ascii=False)))
        return response
