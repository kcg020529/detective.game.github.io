"""Single-character question drafts; defaults to the selected YB-3."""
import argparse
import csv
import json
from collections import Counter

from experiments.evaluation.build_question_sets_v2 import ROOT, load_source, make_set, validate

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--character-id', choices=[f'YB-{n}' for n in range(1, 7)], default='YB-3')
    args = parser.parse_args()
    character = args.character_id
    tag = character.replace('-', '')
    out = ROOT / f'experiments/evaluation/questions_game_data_v3_{tag.lower()}'
    records, policy, source_hash = load_source()
    manifest = dict(status='draft_unreviewed', source_sha256=source_hash, character_id=character,
                    total_cases=450, configurations=3, planned_attempts=1350, sets=[])
    all_ids = set()
    if not args.check:
        out.mkdir(parents=True, exist_ok=True)
    for role in ('std', 'grad', 'prof'):
        if args.check:
            cases = json.loads((out / f'{role}.json').read_text(encoding='utf-8'))
        else:
            cases = make_set(records, policy, role, character_id=character)
            for c in cases:
                c['id'] = c['id'].replace('V2-', f'V3-{tag}-', 1)
                if c.get('pair_id'):
                    c['pair_id'] = c['pair_id'].replace('V2-', f'V3-{tag}-', 1)
        validate(cases, records, policy, role)
        assert all(c['character_id'] == character for c in cases)
        assert all(c['id'] not in all_ids for c in cases)
        all_ids.update(c['id'] for c in cases)
        if not args.check:
            (out / f'{role}.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            with (out / f'{role}.csv').open('w', encoding='utf-8-sig', newline='') as f:
                fields = ['id', 'kind', 'category_label', 'day', 'character_id', 'question', 'target_id',
                          'expected_level', 'pair_id', 'review']
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(cases)
            manifest['sets'].append(dict(role=role, file=f'{role}.json', count=len(cases),
                categories=dict(Counter(c['category_label'] for c in cases))))
    assert len(all_ids) == 450
    if not args.check:
        (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'PASS: {character} only, 450 cases, role balance 50/100, target permissions and 30 Day pairs')


if __name__ == '__main__':
    main()
