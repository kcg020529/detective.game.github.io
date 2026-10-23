# I01 - Save API (Save·메모·Day 진행)

> 담당: J. 기능 단위로 나눠서 Save 기능은 화면·서버·DB를 J가 같이 맡음. 회원가입·로그인·로그아웃은 선영.

1. FastAPI 기본 틀 (`backend/api/main.py`)
   - 경로 `/api/v1`, CORS(GitHub Pages·로컬 프론트 주소, 쿠키 허용), POST·PUT의 `Origin` 확인
   - 오류는 프론트가 읽는 `{error: {code, message, request_id}}` 모양으로 통일
2. DB 연결 (`backend/api/db.py`, PyMySQL, 용범 적재 도구와 같은 환경 변수)
3. 임시 로그인 사용자 (`backend/api/current_user.py`)
   - 선영 세션 코드가 들어오면 이 파일만 교체
4. Save API (`backend/api/saves.py`)
   - Save 목록·만들기·덮어쓰기·불러오기, 메모 저장, Day 진행
   - Save는 계정마다 따로, 최대 3개 (`saves.user_id`, 슬롯 1~3). 다른 계정 Save는 404
5. 같은 요청 다시 보내기 기록 테이블 `010_request_log.sql`
6. 시험 (`tests/api`, 실제 로컬 MariaDB) + 프론트와 실제 서버 연결 확인
7. 선영 로그인과 합치기 (세션으로 `current_user` 교체, `GET /auth/me`)
