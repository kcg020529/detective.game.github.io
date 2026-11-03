# LF 줄바꿈과 동결 결과 검증

저장소의 `.gitattributes`에 따라 텍스트 파일은 LF로 저장한다.

2026-11-03 변환에서는 질문, 답변, 판정, 수치와 기존 manifest의 해시 문자열을 수정하지 않았다. 결과 파일은 CRLF 바이트를 LF로 바꾼 것 외에는 스테이징된 원본과 같다.

과거 manifest에는 Windows CRLF 파일의 SHA-256도 있다. `frozen_hashes.verify_frozen_hash()`는 현재 바이트의 해시를 먼저 확인하고, 다르면 같은 텍스트를 LF/CRLF로 표현한 두 해시만 허용한다. 공백·본문·BOM·마지막 줄바꿈 변경은 허용하지 않는다. 기존 해시를 새 값으로 덮어쓰거나 결과를 재채점하지 않는다.

검증은 `python -m experiments.evaluation.build_grading_keys --check`와 `tests/evaluation/test_frozen_hashes.py`로 수행한다. 기존 adjudicate 실행기는 결과를 다시 쓰므로 보존된 결과를 확인하려는 목적으로 실행하지 않는다.
