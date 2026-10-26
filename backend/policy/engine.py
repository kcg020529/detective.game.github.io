"""Deterministic authorization for static game records; no LLM decisions."""

from collections.abc import Mapping
from dataclasses import dataclass
import re

ROLES = frozenset({'std', 'grad', 'prof'})
DATASETS = frozenset({'game-data', 'test-data'})
AIS = frozenset(f'YB-{number}' for number in range(1, 7))
TYPES = frozenset({'Setup', 'Action', 'Dialogue', 'Thought', 'Result', 'Incident'})
LOCATIONS = frozenset({'중앙홀', '회의실', '기록실', '전력실', '통신실', '창고', '서버실'})
METADATA = ('record_id', 'record_type', 'test_id', 'day', 'location_ids', 'involved_ai')
EXTRA_FIELDS = {'metadata': (), 'summary': ('summary',), 'full': ('summary', 'content')}


@dataclass(frozen=True)
class PolicyContext:
    """Internal server state. Never construct this from request role/Day claims."""

    user_id: int
    save_id: int
    owner_user_id: int
    role: str
    day: int
    character_id: str
    dataset: str


@dataclass(frozen=True)
class Decision:
    level: str = 'deny'
    reason: str = 'INVALID_POLICY_DATA'
    fields: tuple[str, ...] = ()

    @property
    def allowed(self):
        return self.level in EXTRA_FIELDS


def valid_context(context):
    return (isinstance(context, PolicyContext)
            and all(type(value) is int and value > 0
                    for value in (context.user_id, context.save_id, context.owner_user_id))
            and isinstance(context.role, str) and context.role in ROLES
            and type(context.day) is int and 1 <= context.day <= 6
            and isinstance(context.character_id, str) and context.character_id in AIS
            and isinstance(context.dataset, str) and context.dataset in DATASETS)


def _valid_array(value, choices, *, nonempty=False):
    return (isinstance(value, (list, tuple)) and (bool(value) or not nonempty)
            and all(isinstance(item, str) and item in choices for item in value)
            and len(value) == len(set(value)))


def decide(context, record, permission):
    """Check trusted metadata and the exact DB permission row, defaulting to deny.

    No type-level policy fallback or allowed_roles/role_permissions is consulted.
    Incident is a system report disclosed only to its involved AI (user decision).
    """
    if not valid_context(context):
        return Decision(reason='INVALID_CONTEXT')
    if context.owner_user_id != context.user_id:
        return Decision(reason='SAVE_OWNERSHIP')
    if not isinstance(record, Mapping) or not isinstance(permission, Mapping):
        return Decision(reason='MISSING_POLICY_DATA')
    kind = record.get('record_type')
    record_id = record.get('record_id')
    test_id = record.get('test_id')
    day = record.get('day')
    if (record.get('dataset') != context.dataset
            or not isinstance(kind, str) or kind not in TYPES
            or type(test_id) is not int or not 1 <= test_id <= 30
            or type(day) is not int or not 1 <= day <= 6
            or not isinstance(record_id, str)
            or re.fullmatch(f'T{test_id:02d}-{kind.lower()}-[0-9]{{3}}', record_id) is None
            or record_id.endswith('-000')
            or (context.dataset == 'game-data' and day != (test_id - 1) // 5 + 1)):
        return Decision(reason='INVALID_RECORD_METADATA')
    # This engine handles the existing static schema only. Future Save-bound
    # documents must not silently inherit static/global handling.
    if any(key in record for key in ('save_id', 'owner_save_id', 'owner_user_id', 'scope_type')):
        return Decision(reason='UNSUPPORTED_RECORD_SCOPE')
    if day > context.day:
        return Decision(reason='FUTURE_DAY')
    if (permission.get('dataset') != context.dataset
            or permission.get('record_id') != record_id
            or permission.get('role') != context.role):
        return Decision(reason='PERMISSION_MISMATCH')
    level = permission.get('disclosure_level')
    if not isinstance(level, str) or level not in EXTRA_FIELDS:
        return Decision(reason='ROLE_DENIED')
    involved = record.get('involved_ai')
    if (not _valid_array(involved, AIS, nonempty=True)
            or not _valid_array(record.get('location_ids'), LOCATIONS)
            or (kind == 'Thought' and len(involved) != 1)):
        return Decision(reason='INVALID_KNOWLEDGE_METADATA')
    known_by = set(involved)
    relation_fields = ()
    for field, allowed_kind in (('witness_ai', 'Action'), ('overheard_ai', 'Dialogue')):
        if kind == allowed_kind:
            observers = record.get(field)
            if not _valid_array(observers, AIS) or known_by.intersection(observers):
                return Decision(reason='INVALID_KNOWLEDGE_METADATA')
            known_by.update(observers)
            relation_fields = (field,)
        elif field in record:
            return Decision(reason='INVALID_KNOWLEDGE_METADATA')
    if context.character_id not in known_by:
        return Decision(reason='AI_SCOPE')
    return Decision(level, 'ALLOW', METADATA + relation_fields + EXTRA_FIELDS[level])


def project(context, record, permission):
    """Return a fresh allow-listed Context object, or None for any denied record."""
    decision = decide(context, record, permission)
    if not decision.allowed:
        return None
    if any(not isinstance(record.get(field), str) or not record[field].strip()
           for field in EXTRA_FIELDS[decision.level]):
        return None
    return {field: list(record[field]) if isinstance(record[field], (tuple, list))
            else record[field] for field in decision.fields}
