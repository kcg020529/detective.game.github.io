# K01 - Docker Compose 로컬 실행 환경

1. MariaDB·Qdrant를 Docker Compose 하나로 실행
   - 팀원 누구나 `.env` 작성 후 명령 한 줄로 같은 버전·설정의 DB를 띄울 수 있게 함 (MASTER 9.2 로컬 완전 실행)
2. 이미지 버전 고정, 자동 재시작, 이름 있는 데이터 볼륨
3. 비밀번호는 `.env`로만 받고 저장소에는 `.env.example`만 둠
4. 포트는 127.0.0.1에만 열어 외부 접속 차단
5. MariaDB 초기 SQL 자동 실행 경로 준비
   - 테이블 스키마 작성은 B 담당. 경로만 제공
6. 실행·접속·중지·초기화 안내 문서
7. FastAPI·프론트·Grafana 서비스 추가 (예정, 각 서비스 구현 후)

# K02 - 앱 전체 Docker Compose 실행

1. 백엔드 API와 프론트(nginx)를 기존 MariaDB·Qdrant Compose에 추가해 `docker compose up -d` 한 번으로 게임 전체를 로컬에서 띄운다.
2. 프론트와 API를 같은 주소(`/api/v1` 프록시)로 묶어 로컬 로그인 쿠키·CORS 문제를 없앤다.
3. 코드 수정이 다시 빌드 없이 반영되게 소스 폴더를 연결한다.
4. 필요할 때 실행하는 도구: `migrate`(새 SQL만 적용), `load-data`(게임 데이터 적재), `rag-index`(Qdrant 색인).
5. 빈 볼륨으로 팀원 첫 실행을 따라 해 보고, 기존 DB도 데이터 손실 없이 이어지는지 확인한다.

# K03 - 채팅용 DeepSeek 키를 Compose에 전달

1. `api` 서비스에 캐릭터 AI·Planner용 DeepSeek 키 환경변수를 전달한다. 키는 비워도 서버가 뜨고 채팅만 503이 되도록 선택 값으로 둔다.
