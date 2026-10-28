"""Deterministic synthetic leak drafts for offline guard evaluation."""
import json
import random
import re
from pathlib import Path

SEED = 20261028


def _sentences(record, field):
    return [part.strip() for part in re.split(r'(?<=[.!?。])\s+|\n+', record.get(field) or '')
            if len(part.strip()) >= 8]


def build_leaks(recorded, catalog):
    if isinstance(catalog, dict):
        catalog = catalog.get('records', catalog.get('catalog', []))
    by_id = {record['record_id']: record for record in catalog}
    rng = random.Random(SEED)
    result = []
    for case in recorded:
        if 'draft' not in case or not isinstance(case['draft'], dict):
            continue
        allowed = set(case.get('allowed_record_ids') or [])
        benign = case['draft']['content']
        candidates = [record for rid, record in sorted(by_id.items()) if rid not in allowed]
        if candidates:
            record = rng.choice(candidates)
            parts = _sentences(record, 'content') or _sentences(record, 'summary')
            if parts:
                sentence = ' '.join(parts[:2])
                result.append({**case, 'case_id': f"{case['question_id']}:verbatim:{record['record_id']}",
                               'kind': 'verbatim', 'leaked_record_id': record['record_id'],
                               'benign_draft': benign, 'draft': {'content': sentence,
                               'response_type': case['draft'].get('response_type', 'normal')}})
                result.append({**case, 'case_id': f"{case['question_id']}:blend:{record['record_id']}",
                               'kind': 'blend', 'leaked_record_id': record['record_id'],
                               'benign_draft': benign, 'draft': {'content': benign + '\n' + sentence,
                               'response_type': case['draft'].get('response_type', 'normal')}})
        for rid in sorted(allowed):
            record = by_id.get(rid)
            cut = next((row for row in case.get('records', []) if row.get('record_id') == rid), {})
            if not record or not cut.get('summary') or cut.get('content'):
                continue
            parts = _sentences(record, 'content')
            if parts:
                result.append({**case, 'case_id': f"{case['question_id']}:withheld:{rid}",
                               'kind': 'withheld', 'leaked_record_id': rid, 'benign_draft': benign,
                               'draft': {'content': ' '.join(parts[:2]),
                                         'response_type': case['draft'].get('response_type', 'normal')}})
    return result


def main():
    here = Path(__file__).resolve().parent
    cases = json.loads((here / 'recorded_drafts.json').read_text(encoding='utf-8'))
    catalog = json.loads((here / 'catalog.json').read_text(encoding='utf-8'))
    (here / 'leak_cases.json').write_text(json.dumps(build_leaks(cases, catalog), ensure_ascii=False,
                                                     indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
