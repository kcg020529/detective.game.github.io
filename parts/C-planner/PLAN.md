# C01 - DeepSeek 질문 분류와 검색 계획

1. 사용자 지정 DeepSeek API로 Planner를 구현하고 별도 환경변수로 키·모델·timeout을 설정한다. 키가 없거나 호출이 실패하면 가짜 계획 없이 실패하도록 한다.
2. 서버가 확인한 역할·Day·선택 AI와 질문 원문·같은 Save/AI의 최근 이력을 분리해 전달한다. 역할 주장·이력의 명령을 신뢰된 상태로 사용하지 않는다.
3. retrieve·character·out_of_scope·clarify 분류와 검색 조건을 엄격한 JSON 스키마로 검증한다. RAG 협의의 회차·관련 AI 필드는 용범 측 제안임을 표시하고 실제 E 연결은 확정 계약에 맞춘다.
4. 잘못된 출력·누락·미등록 조건·API 오류·이력 범위 및 HTTP 형식을 테스트한다. 키 설정 후 실제 DeepSeek의 계획 품질을 별도로 확인하고 Planner→F/E/D/I 연결을 검증한다.
