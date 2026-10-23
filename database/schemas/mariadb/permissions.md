# 대화 및 권한 테이블 계약

`004_chat_messages.sql`, `005_user_roles.sql`, `006_document_permissions.sql`의 설계 계약이다. 실제 DB 적용·API 연동은 미검증이다.

## chat_messages

사용자 질문과 AI 답변은 각각 한 행으로 저장한다. `save_id`로 Save와 소유 사용자를 식별하고, `ai_id`는 사용자 질문에도 대화 상대 AI를 지정한다. `(save_id, ai_id)` 조건으로 조회해 `message_id` 순으로 정렬한다. 사용자 메시지는 `response_type=NULL`, AI 답변은 `normal`, `partial`, `restricted`, `unknown` 중 하나를 저장한다. 타이핑 애니메이션 상태는 저장하지 않는다.

Save 삭제 시 이력도 삭제된다. 서버는 요청자의 Save 소유권을 확인해야 하며 다른 Save의 이력을 Context로 사용하지 않는다. 허용된 최종 답변만 저장하고 가드 처리 전 원출력·차단된 원문은 저장하지 않는다. 과거 이력 역시 신뢰할 수 있는 권한 근거가 아니며 현재 권한·Day에 따라 Context 사용 가능 여부를 확인해야 한다.

## user_roles

계정별 선택 가능한 역할을 `(user_id, role)`로 저장한다. 동일 계정에 여러 역할을 부여할 수 있다. 가입 시 기본 부여 역할은 아직 미확정이며 SQL은 역할을 자동 부여하지 않는다.

Save 생성·재개와 이후 인가 요청 시 서버는 Save에 저장된 역할이 현재 계정의 허용 목록에도 있는지 확인해야 한다. 역할이 회수되면 기존 Save의 역할을 다른 역할로 자동 변경하지 않고 해당 역할의 이용을 거부한다. 기존 `saves.role`은 유지하며 이 조건은 현재 FK로 강제하지 않는다.

## document_permissions

`(dataset, record_id, role)`에 공개 수준 하나를 저장한다. 권한 행이 없거나 판정에 실패하면 `deny`다. 수준은 문자열의 정렬 순서로 비교하지 않고 명시적인 필드 허용 목록으로 해석한다.

| 수준 | 허용 필드 |
|---|---|
| `full` | 기본 메타데이터 + AI 관계 정보 + summary + content |
| `summary` | 기본 메타데이터 + AI 관계 정보 + summary |
| `metadata` | 기본 메타데이터 + AI 관계 정보 |
| `basic_metadata` | record_id, record_type, test_id, day |
| `deny` | 없음. 문서 존재·ID도 응답이나 모델 Context에 제공하지 않음 |

AI 관계 정보는 involved_ai와 해당 유형에 존재하는 witness_ai·overheard_ai다. Action과 Dialogue 외 유형에는 관찰 필드를 요구하지 않는다. 해당 유형에서 관찰자가 없으면 빈 배열이며, 필수 필드 누락은 적재 오류로 구분해야 한다.

추가된 location_ids는 metadata·summary·full 수준에서 제공하는 장소 메타데이터에 포함한다. basic_metadata의 허용 필드는 기존 네 필드만 유지하며 장소는 포함하지 않는다. content에 기록된 AI별 초기 위치는 full에서만 제공한다.

서버는 공개 수준에 맞춰 DB 조회 결과를 투영한 뒤 모델 Context와 API 응답을 구성해야 한다. summary 수준에서 content를 전달한 뒤 출력만 가리는 방식은 허용하지 않는다. Day·AI 지식 범위·Save 소유권·계정 허용 역할도 별도로 모두 확인한다. summary에도 더 높은 수준의 비밀이 섞이지 않도록 콘텐츠 검수가 필요하다.

`document_permissions`를 문서·역할 공개 수준의 유일한 판정 원천으로 사용한다. 기존 `game_record_allowed_roles`는 초기 설계의 레거시 테이블로 남겨 두되 인가·fallback에는 사용하지 않는다. 기존 데이터 삭제나 권한 변환은 이 SQL에서 수행하지 않는다. 실제 이관 후 레거시 테이블 제거는 별도 마이그레이션으로 진행한다.

테스트 JSON의 allowed_roles는 이진 허용 목록이라 다섯 공개 수준을 결정할 수 없다. 적재 시 공개 수준을 별도로 명시해야 하며 기존 허용 역할을 자동으로 full에 매핑하지 않는다. 현재 권한 데이터·이관 도구는 없다.
