# 프론트엔드 브라우저 검사

- `check_flow.py`: 로그인부터 기록 선택, 대화, 날짜 진행, 판정, 저장 흐름을 확인합니다.
- `check_errors.py`: API 오류, 재시도, 대기 상태와 세션 복구를 확인합니다.
- `check_http.py`: HTTP 요청 형식, 응답 정규화, 오류와 빈 204 응답을 확인합니다.
- `check_roles.py`: 가입, 역할 선택과 대화 페이지 경계를 확인합니다.
- `check_split.py`: 페이지 경계에서 나뉜 질문과 응답을 출력해 확인합니다.

설치: `pip install -r tests/frontend/requirements.txt`를 실행합니다. Playwright는 설치된 Chrome을 `channel="chrome"`으로 사용합니다.

실행: `python tests/frontend/run_all.py`를 실행합니다. 각 검사는 자체 정적 서버를 사용합니다. 실행 중인 프론트엔드를 쓰려면 `FRONT_URL`을 설정합니다.
