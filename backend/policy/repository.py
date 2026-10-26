"""MariaDB adapter for pre-search scopes and post-search revalidation.

Callers provide an authenticated user ID and a DictCursor connection inside
their request transaction. No HTTP route or authentication replacement is added.
"""

from dataclasses import dataclass

from backend.policy.engine import (
    DATASETS, PolicyContext, decide, project, valid_context,
)


class PolicyDenied(Exception):
    """Invalid request or inaccessible Save; do not return internal details to users."""


class PolicyUnavailable(Exception):
    """DB or policy metadata failure. The caller must not fall back to broad search."""


@dataclass(frozen=True)
class SearchScope:
    dataset: str
    disclosures: tuple[tuple[str, str], ...]

    @property
    def record_ids(self):
        return tuple(record_id for record_id, _ in self.disclosures)


class PolicyRepository:
    def __init__(self, connection):
        self.connection = connection

    def _context(self, cursor, user_id, save_id, character_id, dataset):
        if (type(user_id) is not int or user_id <= 0
                or type(save_id) is not int or save_id <= 0
                or not isinstance(dataset, str) or dataset not in DATASETS):
            raise PolicyDenied('INVALID_REQUEST')
        cursor.execute('SELECT user_id, save_id, role, day FROM saves '
                       'WHERE user_id = %s AND save_id = %s', (user_id, save_id))
        save = cursor.fetchone()
        if not save:
            raise PolicyDenied('SAVE_NOT_FOUND')
        context = PolicyContext(user_id, save['save_id'], save['user_id'], save['role'],
                                save['day'], character_id, dataset)
        if (not valid_context(context) or context.owner_user_id != user_id
                or context.save_id != save_id):
            raise PolicyDenied('INVALID_SERVER_STATE')
        return context

    def _metadata(self, cursor, context, record_ids=None):
        suffix = ''
        params = (context.dataset,)
        if record_ids is not None:
            suffix = ' AND r.record_id IN (' + ','.join(['%s'] * len(record_ids)) + ')'
            params += record_ids
        cursor.execute(
            'SELECT r.dataset, r.record_id, r.record_type, r.test_id, r.day, '
            'p.role AS permission_role, p.disclosure_level FROM game_records r '
            'LEFT JOIN document_permissions p ON p.dataset = r.dataset '
            'AND p.record_id = r.record_id AND p.role = %s '
            'WHERE r.dataset = %s' + suffix, (context.role, *params))
        records, permissions = {}, {}
        for row in cursor.fetchall():
            record_id = row['record_id']
            if record_id in records:
                raise PolicyUnavailable('DUPLICATE_POLICY_ROWS')
            record = {key: row[key] for key in
                      ('dataset', 'record_id', 'record_type', 'test_id', 'day')}
            record.update(involved_ai=[], location_ids=[])
            if row['record_type'] == 'Action':
                record['witness_ai'] = []
            elif row['record_type'] == 'Dialogue':
                record['overheard_ai'] = []
            records[record_id] = record
            permissions[record_id] = dict(dataset=row['dataset'], record_id=record_id,
                                          role=row['permission_role'],
                                          disclosure_level=row['disclosure_level'])
        if not records:
            return records, permissions
        cursor.execute(
            'SELECT a.record_id, a.record_type, a.ai_id, a.relation_kind '
            'FROM game_record_ai a JOIN game_records r ON r.dataset = a.dataset '
            'AND r.record_id = a.record_id WHERE r.dataset = %s' + suffix, params)
        fields = {'involved': 'involved_ai', 'witness': 'witness_ai', 'overheard': 'overheard_ai'}
        for row in cursor.fetchall():
            record = records.get(row['record_id'])
            field = fields.get(row['relation_kind'])
            if (record is None or row['record_type'] != record['record_type']
                    or field not in record):
                raise PolicyUnavailable('INVALID_AI_RELATION')
            record[field].append(row['ai_id'])
        cursor.execute(
            'SELECT l.record_id, l.location_id FROM game_record_locations l '
            'JOIN game_records r ON r.dataset = l.dataset AND r.record_id = l.record_id '
            'WHERE r.dataset = %s' + suffix, params)
        for row in cursor.fetchall():
            if row['record_id'] not in records:
                raise PolicyUnavailable('INVALID_LOCATION_RELATION')
            records[row['record_id']]['location_ids'].append(row['location_id'])
        return records, permissions

    def search_scope(self, *, user_id, save_id, character_id, dataset='game-data'):
        """Return allowed keys/levels only; no summaries or bodies are queried."""
        try:
            with self.connection.cursor() as cursor:
                context = self._context(cursor, user_id, save_id, character_id, dataset)
                records, permissions = self._metadata(cursor, context)
                allowed = []
                for record_id, record in sorted(records.items()):
                    decision = decide(context, record, permissions[record_id])
                    if decision.allowed:
                        allowed.append((record_id, decision.level))
                return SearchScope(context.dataset, tuple(allowed))
        except (PolicyDenied, PolicyUnavailable):
            raise
        except Exception:
            raise PolicyUnavailable('POLICY_LOOKUP_FAILED') from None

    def resolve(self, *, user_id, save_id, character_id, record_ids, dataset='game-data'):
        """Reload server state and DB policy for untrusted retrieval candidate IDs.

        Query only the permitted textual columns, then project before returning.
        Missing/denied records are omitted without revealing their existence.
        """
        if (not isinstance(record_ids, (list, tuple)) or len(record_ids) > 100
                or any(not isinstance(value, str) or not 1 <= len(value) <= 64
                       for value in record_ids)):
            raise PolicyDenied('INVALID_CANDIDATE_IDS')
        ids = tuple(dict.fromkeys(record_ids))
        try:
            with self.connection.cursor() as cursor:
                context = self._context(cursor, user_id, save_id, character_id, dataset)
                if not ids:
                    return []
                records, permissions = self._metadata(cursor, context, ids)
                result = []
                for record_id in ids:
                    if record_id not in records:
                        continue
                    record, permission = records[record_id], permissions[record_id]
                    decision = decide(context, record, permission)
                    if not decision.allowed:
                        continue
                    columns = tuple(field for field in ('summary', 'content')
                                    if field in decision.fields)
                    if columns:
                        cursor.execute('SELECT ' + ', '.join(columns) + ' FROM game_records '
                                       'WHERE dataset = %s AND record_id = %s',
                                       (context.dataset, record_id))
                        body = cursor.fetchone()
                        if body is None:
                            raise PolicyUnavailable('RECORD_CHANGED')
                        record.update({field: body.get(field) for field in columns})
                    safe = project(context, record, permission)
                    if safe is None:
                        raise PolicyUnavailable('INVALID_DISCLOSED_FIELDS')
                    result.append(safe)
                return result
        except (PolicyDenied, PolicyUnavailable):
            raise
        except Exception:
            raise PolicyUnavailable('POLICY_LOOKUP_FAILED') from None
