# 게임 기록 역할별 공개 표

`game_record_permissions.json`은 MASTER §5.1과 [역할별 권한 매트릭스](../../docs/interfaces/역할별_권한_매트릭스.md)의 확정 표를 적재 도구가 읽는 설정이다. 여섯 기록 종류와 세 역할을 모두 명시해야 하며 공개 수준은 full·summary·metadata·deny만 허용한다. 누락·알 수 없는 값은 DB 쓰기 전에 오류로 처리한다.

이 표는 적재 시 `document_permissions`를 작성하는 기준이다. 런타임의 권한 행 누락을 보충하거나 Day·AI 지식·Save 확인을 생략하는 용도로 사용하지 않는다. game-data 원본의 allowed_roles도 deny가 아닌 역할 목록으로 맞추되, 요약·메타데이터·본문을 구별하지 못하므로 인가 근거로 사용하지 않는다. 검수한 기록별 role_permissions 예외는 이 표보다 우선하고, 해당 객체에 없는 역할은 deny다.

표를 변경하면 문서와 테스트 기대값을 함께 갱신하고 dry-run 공개 건수를 검수한 뒤 대상 DB를 재적재한다. 설정 파일만 수정해서 이미 적재한 DB 권한이 자동 변경되지는 않는다. 실제 실행·이관은 [적재 안내](../loaders/README.md)를 따른다.
