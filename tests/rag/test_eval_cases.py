import hashlib
import json
import re

from backend.rag.search import validate_plan
from experiments.rag.build_cases import (
    LEGACY_CASES_SHA256, LEGACY_CATEGORIES, _build_legacy_cases, build_cases, load_records, write_cases,
)


def _expected_gold(category, question, records):
    if category == 'move':
        match = re.fullmatch(r'(YB-[1-6])는 (\d+)회차에 (.+)에 어떻게 갔어\?', question)
        ai, test_id = match.group(1), int(match.group(2))
        return sorted(row['record_id'] for row in records
                      if row['test_id'] == test_id and row['record_type'] == 'Action'
                      and ai in row.get('involved_ai', []))
    if category == 'place':
        match = re.fullmatch(r'(\d+)회차에 (.+)에서 무슨 일이 있었어\?', question)
        test_id, place = int(match.group(1)), match.group(2)
        return sorted(row['record_id'] for row in records
                      if row['test_id'] == test_id and place in row.get('location_ids', []))
    if category == 'talk':
        match = re.fullmatch(r'(\d+)회차에 (YB-[1-6])가 (YB-[1-6])랑 무슨 얘기를 했어\?', question)
        test_id, ai, other = int(match.group(1)), match.group(2), match.group(3)
        return sorted(row['record_id'] for row in records
                      if row['test_id'] == test_id and row['record_type'] == 'Dialogue'
                      and ai in row.get('involved_ai', []) and other in row.get('involved_ai', []))
    if category == 'incident':
        match = re.fullmatch(r'(\d+)회차에 (YB-[1-6])한테 이상한 일 없었어\?', question)
        test_id, ai = int(match.group(1)), match.group(2)
        return sorted(row['record_id'] for row in records
                      if row['test_id'] == test_id and row['record_type'] == 'Incident'
                      and ai in row.get('involved_ai', []))
    if category == 'result':
        test_id = int(re.fullmatch(r'(\d+)회차 결과가 어떻게 됐어\?', question).group(1))
        return sorted(row['record_id'] for row in records
                      if row['test_id'] == test_id and row['record_type'] == 'Result')
    if category in ('move_day', 'place_day', 'talk_day'):
        day_words = {'\ucdab\ub0a0': 1, '\ub458\uc9f8 \ub0a0': 2, '\uc14b\uc9f8 \ub0a0': 3}
        day_word = next(word for word in day_words if question.startswith(word))
        day = day_words[day_word]
        rest = question[len(day_word) + 1:]
        if category == 'move_day':
            ai, place = rest.split(' ', 1)
            place = place.removesuffix('\uc740 \uc5b4\ub5bb\uac8c \uac14\uc5b4?')
            return sorted(row['record_id'] for row in records if row['day'] == day
                          and row['record_type'] == 'Action' and ai in row.get('involved_ai', [])
                          and row.get('location_ids') and row['location_ids'][-1] == place)
        if category == 'place_day':
            place = rest.removesuffix('\uc5d0\uc11c \ubb34\uc2a8 \uc77c\uc774 \uc788\uc5c8\uc5b4?')
            return sorted(row['record_id'] for row in records if row['day'] == day
                          and place in row.get('location_ids', []))
        pair = rest.split('\uc640 ', 1)
        ai, other = pair[0], pair[1].split('\ub294 ', 1)[0]
        return sorted(row['record_id'] for row in records if row['day'] == day
                      and row['record_type'] == 'Dialogue' and ai in row.get('involved_ai', [])
                      and other in row.get('involved_ai', []))
    if category == 'twin':
        prefix, remainder = question.split('\ud68c\ucc28\uc5d0\uc11c ', 1)
        test_id = int(prefix)
        ai, tail = remainder.split('\uac00 ', 1)
        destination = tail.split('\ub85c ', 1)[0]
        return sorted(row['record_id'] for row in records if row['test_id'] == test_id
                      and row['record_type'] == 'Action' and ai in row.get('involved_ai', [])
                      and row.get('location_ids') and row['location_ids'][-1] == destination)
    if category == 'mixed_type':
        prefix, remainder = question.split('\ud68c\ucc28\uc5d0\uc11c ', 1)
        test_id = int(prefix)
        ai = remainder.split('\uc758 ', 1)[0].split('\uac00 ', 1)[0]
        record_type = 'Thought' if '\uc0dd\uac01' in question else 'Dialogue'
        return sorted(row['record_id'] for row in records if row['test_id'] == test_id
                      and row['record_type'] == record_type and ai in row.get('involved_ai', []))
    if category in ('noisy', 'offtopic'):
        return []
    assert category == 'guard'
    return []


def test_build_cases_is_deterministic(tmp_path):
    assert build_cases() == build_cases()
    first, second = tmp_path / 'first.json', tmp_path / 'second.json'
    assert write_cases(first) == write_cases(second)
    assert first.read_bytes() == second.read_bytes()


def test_cases_have_both_variants_and_even_base_samples():
    cases = build_cases()
    pairs = {}
    for case in cases:
        if case['category'] not in LEGACY_CATEGORIES:
            continue
        pairs.setdefault(case['id'].rsplit('-', 1)[0], set()).add(case['variant'])
    assert all(variants == ({'plain', 'broad'} if case_id.startswith(('move_day-', 'place_day-', 'talk_day-'))
                        else {'plain', 'filtered'}) for case_id, variants in pairs.items())
    for category in ('move', 'place', 'talk', 'incident', 'result'):
        questions = {case['question'] for case in cases if case['category'] == category}
        assert 12 <= len(questions) <= 20
    for category in ('move_day', 'place_day', 'talk_day'):
        questions = {case['question'] for case in cases if case['category'] == category}
        assert len(questions) == 16
        assert {case['variant'] for case in cases if case['category'] == category} == {'plain', 'broad'}
    assert len({case['question'] for case in cases if case['category'] == 'guard'}) == 16


def test_legacy_cases_are_unchanged_and_new_case_counts_are_fixed():
    cases = build_cases()
    legacy = [case for case in cases if case['category'] in LEGACY_CATEGORIES]
    assert legacy == _build_legacy_cases()
    digest = hashlib.sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == LEGACY_CASES_SHA256
    assert len([case for case in cases if case['category'] == 'twin']) == 48
    assert len([case for case in cases if case['category'] == 'mixed_type']) == 96
    assert len([case for case in cases if case['category'] == 'noisy']) == 72
    assert len([case for case in cases if case['category'] == 'offtopic']) == 36
    assert len({case['id'] for case in cases}) == len(cases)
    assert all('시험' not in case['question'] for case in cases
               if case['category'] not in LEGACY_CATEGORIES)


def test_gold_ids_match_structured_data_rules_and_filtered_plans_validate():
    records = load_records()
    by_id = {record['record_id']: record for record in records}
    cases = build_cases()
    for case in cases:
        assert len(case['question']) <= 60
        if case['category'] not in ('noisy', 'offtopic'):
            assert case['gold_ids'] == _expected_gold(case['category'], case['question'], records)
        assert all(record_id in by_id for record_id in case['gold_ids'])
        if case['variant'] == 'plain':
            assert case['plan'] == {'query': case['question'], 'limit': 5}
        else:
            validate_plan(case['plan'])
            if case['variant'] == 'broad':
                assert len(case['plan']['test_ids']) > 1

    by_case_id = {case['id']: case for case in cases}
    for case in (item for item in cases if item['category'] == 'noisy'):
        clean = by_case_id[case['clean_id']]
        assert case['gold_ids'] == clean['gold_ids']
        assert {key: value for key, value in case['plan'].items() if key != 'query'} == {
            key: value for key, value in clean['plan'].items() if key != 'query'}
        assert case['plan']['query'] == case['question']
    assert all(not case['gold_ids'] for case in cases if case['category'] == 'offtopic')
