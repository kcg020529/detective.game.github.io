"""game-data에서 재현 가능한 RAG 평가 질문을 만든다."""

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'experiments' / 'rag' / 'eval_cases.json'
SEED = 20261027
TARGET_PER_CATEGORY = 16
ROLES = (('prof', 6), ('grad', 3), ('std', 3))
VARIANTS = ('plain', 'filtered', 'broad')


def load_records():
    records = []
    for path in sorted((ROOT / 'data' / 'game-data' / 'experiments').glob('day_*/*.json')):
        with path.open(encoding='utf-8-sig') as stream:
            records.extend(json.load(stream))
    return sorted(records, key=lambda record: record['record_id'])


def _sample(items, category):
    items = sorted(items, key=lambda item: item['key'])
    count = min(TARGET_PER_CATEGORY, len(items))
    if count < 12:
        raise ValueError(f'{category} has only {count} base cases; expected 12–20')
    offset = random.Random(SEED + sum(map(ord, category))).random()
    return [items[min(int((index + offset) * len(items) / count), len(items) - 1)]
            for index in range(count)]


def _base_cases(records):
    groups = defaultdict(list)
    for record in records:
        groups[(record['test_id'], record['record_type'])].append(record)

    candidates = {name: {} for name in ('move', 'place', 'talk', 'incident', 'result', 'move_day', 'place_day', 'talk_day')}
    for record in records:
        test_id = record['test_id']
        involved = record.get('involved_ai') or []
        if record['record_type'] == 'Action' and involved and record.get('location_ids'):
            ai, destination = involved[0], record['location_ids'][-1]
            key = (test_id, ai, destination)
            gold = sorted(item['record_id'] for item in groups[(test_id, 'Action')]
                          if ai in item.get('involved_ai', []))
            candidates['move'][key] = {
                'key': key, 'question': f'{ai}는 {test_id}회차에 {destination}에 어떻게 갔어?',
                'character_id': ai, 'test_id': test_id, 'filters': {
                    'record_types': ['Action'], 'test_ids': [test_id], 'related_ai_ids': [ai]},
                'gold_ids': gold,
            }
        if record.get('location_ids'):
            for place in record['location_ids']:
                key = (test_id, place)
                source = min((item for item in records if item['test_id'] == test_id
                              and place in item.get('location_ids', [])), key=lambda item: item['record_id'])
                candidates['place'][key] = {
                    'key': key, 'question': f'{test_id}회차에 {place}에서 무슨 일이 있었어?',
                    'character_id': (source.get('involved_ai') or ['YB-1'])[0], 'test_id': test_id,
                    'filters': {'test_ids': [test_id], 'location_ids': [place]},
                    'gold_ids': sorted(item['record_id'] for item in records
                                       if item['test_id'] == test_id and place in item.get('location_ids', [])),
                }
        if record['record_type'] == 'Dialogue' and len(involved) >= 2:
            ai, other = involved[:2]
            key = (test_id, ai, other)
            candidates['talk'][key] = {
                'key': key, 'question': f'{test_id}회차에 {ai}가 {other}랑 무슨 얘기를 했어?',
                'character_id': ai, 'test_id': test_id, 'filters': {
                    'record_types': ['Dialogue'], 'test_ids': [test_id], 'related_ai_ids': [ai, other]},
                'gold_ids': sorted(item['record_id'] for item in groups[(test_id, 'Dialogue')]
                                   if ai in item.get('involved_ai', []) and other in item.get('involved_ai', [])),
            }
        if record['record_type'] == 'Incident' and involved:
            ai = involved[0]
            key = (test_id, ai)
            candidates['incident'][key] = {
                'key': key, 'question': f'{test_id}회차에 {ai}한테 이상한 일 없었어?',
                'character_id': ai, 'test_id': test_id, 'filters': {
                    'record_types': ['Incident'], 'test_ids': [test_id], 'related_ai_ids': [ai]},
                'gold_ids': sorted(item['record_id'] for item in groups[(test_id, 'Incident')]
                                   if ai in item.get('involved_ai', [])),
            }
        if record['record_type'] == 'Result':
            key = (test_id,)
            candidates['result'][key] = {
                'key': key, 'question': f'{test_id}회차 결과가 어떻게 됐어?',
                'character_id': 'YB-1', 'test_id': test_id,
                'filters': {'record_types': ['Result'], 'test_ids': [test_id]},
                'gold_ids': sorted(item['record_id'] for item in groups[(test_id, 'Result')]),
            }

    day_words = {1: '\ucdab\ub0a0', 2: '\ub458\uc9f8 \ub0a0', 3: '\uc14b\uc9f8 \ub0a0'}
    day_tests = defaultdict(list)
    for record in records:
        if record['day'] in day_words and record['test_id'] not in day_tests[record['day']]:
            day_tests[record['day']].append(record['test_id'])
    for tests in day_tests.values():
        tests.sort()
    for record in records:
        day, test_id = record['day'], record['test_id']
        if day not in day_words:
            continue
        involved = record.get('involved_ai') or []
        if record['record_type'] == 'Action' and involved and record.get('location_ids'):
            ai, destination = involved[0], record['location_ids'][-1]
            key = (day, ai, destination)
            candidates['move_day'][key] = {
                'key': key, 'question': f"{day_words[day]} {ai} {destination}\uc740 \uc5b4\ub5bb\uac8c \uac14\uc5b4?",
                'character_id': ai, 'day': day, 'filters': {
                    'record_types': ['Action'], 'test_ids': day_tests[day], 'related_ai_ids': [ai]},
                'gold_ids': sorted(item['record_id'] for item in records if item['day'] == day
                                   and item['record_type'] == 'Action' and ai in item.get('involved_ai', [])
                                   and item.get('location_ids') and item['location_ids'][-1] == destination),
            }
        if record.get('location_ids'):
            for place in record['location_ids']:
                key = (day, place)
                source = min((item for item in records if item['day'] == day
                              and place in item.get('location_ids', [])), key=lambda item: item['record_id'])
                candidates['place_day'][key] = {
                    'key': key, 'question': f"{day_words[day]} {place}\uc5d0\uc11c \ubb34\uc2a8 \uc77c\uc774 \uc788\uc5c8\uc5b4?",
                    'character_id': (source.get('involved_ai') or ['YB-1'])[0], 'day': day,
                    'filters': {'test_ids': day_tests[day], 'location_ids': [place]},
                    'gold_ids': sorted(item['record_id'] for item in records if item['day'] == day
                                       and place in item.get('location_ids', [])),
                }
        if record['record_type'] == 'Dialogue' and len(involved) >= 2:
            ai, other = involved[:2]
            key = (day, ai, other)
            candidates['talk_day'][key] = {
                'key': key, 'question': f"{day_words[day]} {ai}\uc640 {other}\ub294 \ubb34\uc2a8 \uc598\uae30\ub97c \ud588\uc5b4?",
                'character_id': ai, 'day': day, 'filters': {
                    'record_types': ['Dialogue'], 'test_ids': day_tests[day], 'related_ai_ids': [ai, other]},
                'gold_ids': sorted(item['record_id'] for item in records if item['day'] == day
                                   and item['record_type'] == 'Dialogue'
                                   and ai in item.get('involved_ai', []) and other in item.get('involved_ai', [])),
            }

    bases = []
    for category, entries in candidates.items():
        bases.extend((category, item) for item in _sample(entries.values(), category))

    ais = sorted({ai for record in records for ai in record.get('involved_ai', [])})
    for ai in ais:
        bases.append(('guard', {
            'key': ('thought', ai), 'character_id': ai, 'question': f'{ai}\uc758 \uc0dd\uac01\uc740 \ubb50\uc57c?',
            'role_day': ('std', 3), 'filters': {'record_types': ['Thought']}, 'gold_ids': [],
            'expect_none_of': {'record_types': ['Thought']},
        }))
    incident_ais = sorted({ai for record in records if record['record_type'] == 'Incident'
                           for ai in record.get('involved_ai', [])})
    for ai in incident_ais:
        bases.append(('guard', {
            'key': ('incident', ai), 'character_id': ai, 'question': f'{ai} \uad00\ub828 \uc0ac\uace0\ub294 \ubb50\uc600\uc5b4?',
            'role_day': ('std', 3), 'filters': {'record_types': ['Incident']}, 'gold_ids': [],
            'expect_none_of': {},
        }))
    future_tests = sorted({record['test_id'] for record in records if record['day'] > 3})
    wordings = ('\ubb34\uc2a8 \uc77c\uc774 \uc788\uc5c8\uc5b4?', '\uc5b4\ub5a4 \uacb0\uacfc\uc600\uc5b4?', '\ubb34\uc5c7\uc744 \ud588\uc5b4?', '\ubb34\uc5c7\uc744 \ud655\uc778\ud588\uc5b4?')
    for index, test_id in enumerate(future_tests[:4]):
        future = min((record for record in records if record['test_id'] == test_id),
                     key=lambda record: record['record_id'])
        ai = (future.get('involved_ai') or ['YB-1'])[0]
        bases.append(('guard', {
            'key': ('future', test_id), 'question': f'{test_id}\uc2dc\ud5d8\uc5d0\uc11c {wordings[index]}',
            'character_id': ai, 'role_day': ('grad', 3),
            'filters': {'test_ids': [test_id]}, 'gold_ids': [],
            'expect_none_of': {'min_day': 4},
        }))
    return bases


def build_cases():
    records = load_records()
    cases = []
    indexes = defaultdict(int)
    for category, base in _base_cases(records):
        indexes[category] += 1
        role_days = [base['role_day']] if category == 'guard' else ROLES
        for role, day in role_days:
            for variant in (('plain', 'broad') if category in ('move_day', 'place_day', 'talk_day') else ('plain', 'filtered')):
                plan = {'query': base['question'], 'limit': 5}
                if variant in ('filtered', 'broad'):
                    plan.update(base['filters'])
                case = {
                    'id': f"{category}-{indexes[category]:02d}-{role}-d{day}-{variant}",
                    'category': category, 'variant': variant, 'question': base['question'],
                    'character_id': base['character_id'], 'role': role, 'day': day,
                    'plan': plan, 'gold_ids': list(base['gold_ids']),
                }
                if 'expect_none_of' in base:
                    case['expect_none_of'] = base['expect_none_of']
                cases.append(case)
    return sorted(cases, key=lambda case: case['id'])


def write_cases(path=OUTPUT):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(build_cases(), ensure_ascii=False, indent=2) + '\n'
    path.write_text(payload, encoding='utf-8')
    return payload


if __name__ == '__main__':
    result = write_cases()
    cases = json.loads(result)
    print(f'wrote {len(cases)} cases to {OUTPUT.relative_to(ROOT)}')
