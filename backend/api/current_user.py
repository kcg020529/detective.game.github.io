import os

from fastapi import Depends

from backend.api.db import get_db


def current_user_id(conn=Depends(get_db)) -> int:
    # shortcut: 로그인 붙기 전 임시 사용자. 선영 세션 코드로 교체
    username = os.getenv('KERVION_DEV_USER', 'researcher01')
    with conn.cursor() as cursor:
        cursor.execute('SELECT user_id FROM users WHERE username = %s', (username,))
        row = cursor.fetchone()
        if row:
            return int(row['user_id'])
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, '!') "
            'ON DUPLICATE KEY UPDATE username = VALUES(username)',
            (username,),
        )
        cursor.execute('SELECT user_id FROM users WHERE username = %s', (username,))
        return int(cursor.fetchone()['user_id'])
