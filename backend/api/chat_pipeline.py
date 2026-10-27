"""Chat orchestration. D and G-2 adapters must be explicitly installed by the app."""
import os

from backend.api.errors import ApiError
from backend.planner.service import Planner, PlannerInputError, PlannerUnavailable
from backend.policy.repository import PolicyDenied, PolicyUnavailable


class ChatPipeline:
    def __init__(self, generator=None, output_guard=None):
        self.generator = generator
        self.output_guard = output_guard

    def reply(self, *, conn, question, context, history):
        if self.generator is None or self.output_guard is None:
            raise ApiError(503, 'SERVICE_UNAVAILABLE', '캐릭터 응답·출력 검사 연결이 준비되지 않았습니다.')
        try:
            plan = Planner.from_environment().plan(question, context, history)
            records = []
            if plan.route == 'retrieve':
                from qdrant_client import QdrantClient
                from backend.rag.embedder import FastEmbedder
                from backend.rag.search import search_records
                qdrant = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'))
                try:
                    records = search_records(
                        conn, user_id=context.user_id, save_id=context.save_id,
                        character_id=context.character_id, dataset=context.dataset,
                        plan=plan.search.to_rag_request(), qdrant=qdrant, embedder=FastEmbedder())
                finally:
                    qdrant.close()
            draft = self.generator(question=question, context=context, history=history,
                                   plan=plan, records=records)
            # G-2 returns the approved/replaced final answer, never an unchecked draft.
            final = self.output_guard(draft=draft, context=context, records=records)
            if (not isinstance(final, dict) or set(final) != {'content', 'response_type'}
                    or not isinstance(final['content'], str) or not final['content'].strip()
                    or len(final['content']) > 2000
                    or final['response_type'] not in ('normal', 'partial', 'restricted', 'unknown')):
                raise ApiError(503, 'SERVICE_UNAVAILABLE', '안전한 답변을 준비하지 못했습니다.')
            return final
        except ApiError:
            raise
        except (PlannerInputError, PlannerUnavailable, PolicyDenied, PolicyUnavailable):
            raise ApiError(503, 'SERVICE_UNAVAILABLE', '답변 서비스를 사용할 수 없습니다.') from None
        except Exception:
            # Includes optional RAG dependency/transport and D/G-2 failures.
            raise ApiError(503, 'SERVICE_UNAVAILABLE', '답변 서비스를 사용할 수 없습니다.') from None
