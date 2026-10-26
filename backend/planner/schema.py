"""Strict internal Planner output. No authorization fields are accepted."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CharacterId = Literal['YB-1', 'YB-2', 'YB-3', 'YB-4', 'YB-5', 'YB-6']
RecordType = Literal['Setup', 'Action', 'Dialogue', 'Thought', 'Result', 'Incident']
LocationId = Literal['중앙홀', '회의실', '기록실', '전력실', '통신실', '창고', '서버실']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class SearchPlan(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    record_types: list[RecordType] = Field(max_length=6)
    test_ids: list[Annotated[int, Field(ge=1, le=30)]] = Field(max_length=30)
    location_ids: list[LocationId] = Field(max_length=7)
    related_ai_ids: list[CharacterId] = Field(max_length=6)
    limit: int = Field(ge=1, le=20)

    @field_validator('query')
    @classmethod
    def nonblank_query(cls, value):
        if not value.strip():
            raise ValueError('empty query')
        return value

    @field_validator('record_types', 'test_ids', 'location_ids', 'related_ai_ids')
    @classmethod
    def unique_filters(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('duplicate filters')
        return value

    def to_rag_request(self):
        """Only narrowing search fields, never server identities or permissions."""
        return self.model_dump()


class PlannerResult(StrictModel):
    route: Literal['retrieve', 'character', 'out_of_scope', 'clarify']
    search: SearchPlan | None
    clarification_code: Literal['AMBIGUOUS_REFERENCE', 'INSUFFICIENT_CONTEXT'] | None

    @model_validator(mode='after')
    def consistent_route(self):
        if self.route == 'retrieve':
            if self.search is None or self.clarification_code is not None:
                raise ValueError('retrieve needs search only')
        elif self.route == 'clarify':
            if self.search is not None or self.clarification_code is None:
                raise ValueError('clarify needs a clarification code only')
        elif self.search is not None or self.clarification_code is not None:
            raise ValueError('non-retrieval routes must not contain search')
        return self


class HistoryTurn(StrictModel):
    save_id: int = Field(gt=0)
    character_id: CharacterId
    sender: Literal['user', 'ai']
    content: str = Field(min_length=1, max_length=8000)
