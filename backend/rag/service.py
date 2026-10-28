"""채팅 파이프라인이 쓰는 RAG 진입점.

검색은 search.py가 하고, 여기서는 그 결과를 채팅에서 바로 쓰도록 다듬는다:
- 허용 기록 → Character AI(D)의 memory [{id, text}]
- 결과가 비었을 때의 이유(신호)를 함께 돌려줌
"""

import os
from dataclasses import dataclass, field

from backend.rag.embedder import FastEmbedder
from backend.rag.search import search_with_signal


@dataclass(frozen=True)
class Retrieval:
    records: list    # F가 최종 허용한 기록 (search_records와 같은 값)
    memory: list     # D에 넘길 [{'id', 'text'}]
    signal: str      # search.SIGNAL_OK / SIGNAL_NO_ALLOWED / SIGNAL_NO_MATCH
    id_map: dict = field(default_factory=dict)


def _memory_text(record):
    if record.get('content') or record.get('summary'):
        parts = [record.get('summary'), record.get('content')]
        body = '\n'.join(part.strip() for part in parts if isinstance(part, str) and part.strip())
        if not body:
            return ''
        info = ', '.join(_metadata_parts(record))
        return f'{body}\n[기록 정보] {info}' if info else body
    return _metadata_line(record)


def to_memory(records):
    """허용된 기록을 D의 memory로 바꾼다. 공개 수준에 따라 쓸 수 있는 글만 넣는다.

    full: 요약+본문, summary: 요약만, metadata: 종류·Day·회차·장소·관련 AI를 적은 한 줄.
    기록에 없는 필드는 지어내지 않는다. 이미 F가 잘라 준 필드만 쓰므로 여기서 권한을 넓히지 않는다.
    """
    memory = []
    for record in records:
        record_id = record.get('record_id')
        if not isinstance(record_id, str) or not record_id:
            continue
        text = _memory_text(record)
        if text:
            memory.append({'id': record_id, 'text': text})
    return memory


def build_memory(records):
    memory, id_map = [], {}
    for record in records:
        record_id = record.get('record_id')
        if not isinstance(record_id, str) or not record_id:
            continue
        text = _memory_text(record)
        if text:
            memory_id = f'm{len(memory) + 1}'
            memory.append({'id': memory_id, 'text': text})
            id_map[memory_id] = record_id
    return memory, id_map


def resolve_used(used, id_map):
    if not isinstance(used, (list, tuple)):
        return ([], []) if used is None else ([], [used])
    record_ids, dropped, seen = [], [], set()
    for memory_id in used:
        if isinstance(memory_id, str) and memory_id in id_map:
            record_id = id_map[memory_id]
            if record_id not in seen:
                record_ids.append(record_id)
                seen.add(record_id)
        else:
            dropped.append(memory_id)
    return record_ids, dropped


def _metadata_parts(record):
    parts = []
    if record.get('record_type'):
        parts.append(f"기록 유형 {record['record_type']}")
    if record.get('day') is not None:
        parts.append(f"Day {record['day']}")
    if record.get('test_id') is not None:
        parts.append(f"{record['test_id']}회차")
    places = [p for p in record.get('location_ids') or [] if isinstance(p, str)]
    if places:
        # 장소는 순서 없는 집합이다(DB가 이름순으로 돌려주고, 배열 순서는 이동 방향이 아님). 방향을 추측하지 않게 알린다.
        parts.append(f"장소 {', '.join(places)}" + (' (순서 무관)' if len(places) > 1 else ''))
    ais = [a for a in record.get('involved_ai') or [] if isinstance(a, str)]
    if ais:
        parts.append(f"관련 AI {', '.join(ais)}")
    return parts


def _metadata_line(record):
    parts = _metadata_parts(record)
    return ', '.join(parts) + '.' if parts else ''


def retrieve(conn, *, user_id, save_id, character_id, dataset, plan, qdrant=None, embedder=None):
    """채팅 한 번의 검색. qdrant·embedder를 주지 않으면 QDRANT_URL과 공유 모델을 쓴다."""
    own_client = qdrant is None
    if own_client:
        from qdrant_client import QdrantClient

        qdrant = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'))
    try:
        from backend.api.switches import acl_mode
        if acl_mode(dataset) == 'off':
            from backend.rag.acl_off import search_without_acl
            records, signal = search_without_acl(
                conn, dataset=dataset, plan=plan, qdrant=qdrant, embedder=embedder or FastEmbedder())
        else:
            records, signal = search_with_signal(
                conn, user_id=user_id, save_id=save_id, character_id=character_id, dataset=dataset,
                plan=plan, qdrant=qdrant, embedder=embedder or FastEmbedder())
    finally:
        if own_client:
            qdrant.close()
    memory, id_map = build_memory(records)
    return Retrieval(records, memory, signal, id_map)
