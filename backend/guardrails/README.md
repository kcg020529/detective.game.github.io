# 보안 가드레일

- `input/`: G-1 입력 위험도 검사 (선영). 구현·실행 안내는 `input/README.md`.
- `output/`: G-2 출력 가드레일 (형주). 현재 구현 전이며 패키지 경로만 준비했다.

입력 검사와 출력 검사는 별도 모듈이다. D의 캐릭터 답변 생성도 G-2와 별도 영역이다.

입력 판정과 경고 저장의 호출 방법은 `input/README.md`를 따른다. 채팅 POST는 인증·Save 소유권 확인 뒤 `backend.audit.input_guard_flow.inspect_and_record_input()`을 호출한다.
