# N01 - 종합 보안 성능 비교·평가

1. 2026-11-02 사용자 결정에 따라 직접 작성한 가상 `game-data`를 분리된 실험 환경의 취약 비교군에도 사용할 수 있도록 `MASTER.md`, `README.md`, N 계획을 변경했다. 일반 채팅 API의 game-data ACL-off 제한은 유지한다.
2. `experiments/evaluation/prompt_only.py`에 game-data 명시적 opt-in을 추가하고 `compare_acl.py`에서 데이터셋·외부 케이스 파일을 선택하도록 했다. game-data는 명시적 opt-in과 케이스 파일을 요구하고 Day 1~6을 처리하며 각 결과에 데이터셋을 남긴다. 기존 자동 생성 질문 파일은 실행 시 덮어쓰지 않는다.
3. Docker 이미지에서 `tests/evaluation/test_prompt_only.py`와 `tests/test_switches.py`를 실행해 14건을 통과했다. Python 소스 컴파일도 확인했다. 실제 DB·Qdrant·모델을 이용한 game-data 비교 실험은 실행하지 않았다.
4. 현재 도구는 검색/반환 Context 비교만 수행하며 요청한 세 구성의 가드·최종 응답 비교, 독립 검수된 game-data 200문항, 실험용 DB 구성 및 전체 단계 계측은 미완료다. 기존 비교의 정답은 실제 정책 어댑터에서 산출하므로 독립 정답 검수도 필요하다.
