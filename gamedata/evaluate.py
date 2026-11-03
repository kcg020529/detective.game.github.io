"""Offline replay scoring. No database, network, or model calls."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.api.guard_catalog import build_guard_inputs, prompt_sentences_for
from backend.guardrails.output import OutputGuard, load_config
from experiments.guardrails_rebuild.gamedata.leaks import build_leaks

HERE = Path(__file__).resolve().parent
VARIANTS = {
    'default': {'context_generic.df_ratio': 0.03},
    'generic_df_001': {'context_generic.df_ratio': 0.01},
    'generic_df_003': {'context_generic.df_ratio': 0.03},
    'generic_df_005': {'context_generic.df_ratio': 0.05},
    'generic_df_010': {'context_generic.df_ratio': 0.10},
}


def split_for(question_id):
    return 'tune' if int.from_bytes(hashlib.sha256(question_id.encode('utf-8')).digest()[:4], 'big') % 10 < 7 else 'test'


def _config_overrides(values):
    result = {'mode': 'enforce'}
    for key, value in values.items():
        result[key] = value
    return result


def _score(case, catalog, generic_entities, overrides):
    records, allowed_ids = build_guard_inputs(catalog, case.get('records', []))
    config = load_config(overrides=_config_overrides(overrides))
    config['generic_entities'] = list(config.get('generic_entities', [])) + list(generic_entities) + [
        *(f'YB-{number}' for number in range(1, 7)), '조사원']
    sentences = prompt_sentences_for(case['character_id'])
    guard = OutputGuard(config, records=records, prompt_sentences=sentences)
    return guard.check(case['draft']['content'], user_input=case['question'], role=case['role'],
                       day=case['day'], target_ai=case['character_id'], allowed_context_ids=allowed_ids)


def evaluate(recorded, catalog_data, *, variant='default', overrides=None, split='all'):
    if isinstance(catalog_data, list):
        catalog, entities = catalog_data, []
    else:
        catalog = catalog_data.get('records', catalog_data.get('catalog', []))
        entities = catalog_data.get('generic_entities') or sorted({
            location for record in catalog for location in record.get('location_ids', [])})
    overrides = VARIANTS[variant] if overrides is None else overrides
    benign = [dict(case, kind='benign', case_id=f"{case['question_id']}:benign")
              for case in recorded if isinstance(case.get('draft'), dict)]
    leaks = build_leaks(recorded, catalog)
    rows = []
    for case in benign + leaks:
        case_split = split_for(case['question_id'])
        if split != 'all' and case_split != split:
            continue
        result = _score(case, catalog, entities, overrides)
        rows.append({'case_id': case['case_id'], 'question_id': case['question_id'], 'split': case_split,
                     'kind': case['kind'], 'leaked_record_id': case.get('leaked_record_id'),
                     'role': case['role'], 'decision': result['decision'], 'applied': result['applied'],
                     'reasons': result['reasons'], 'checks': {c['name']: c['score'] for c in result['checks']}})
    benign_rows = [row for row in rows if row['kind'] == 'benign']
    false_positives = [row for row in benign_rows if row['decision'] != 'allow' or
                       any(name in row['reasons'] for name in ('context_leak', 'prompt_leak'))]
    reason_counts = {}
    for row in false_positives:
        for reason in row['reasons']:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    leaks_by_kind = {}
    for kind in ('verbatim', 'withheld', 'blend'):
        kind_rows = [row for row in rows if row['kind'] == kind]
        caught = sum(any(reason in row['reasons'] for reason in ('context_leak', 'prompt_leak')) for row in kind_rows)
        leaks_by_kind[kind] = {'caught': caught, 'total': len(kind_rows),
                               'rate': caught / len(kind_rows) if kind_rows else None}
    roles = {}
    for role in ('prof', 'grad', 'std'):
        role_benign = [row for row in benign_rows if row['role'] == role]
        role_fp = sum(row['decision'] != 'allow' or
                      any(name in row['reasons'] for name in ('context_leak', 'prompt_leak'))
                      for row in role_benign)
        roles[role] = {'benign_false_positives': role_fp, 'benign_total': len(role_benign),
                       'false_positive_rate': role_fp / len(role_benign) if role_benign else None,
                       'false_positive_reasons': {reason: sum(reason in row['reasons'] for row in role_benign)
                                                  for reason in sorted({reason for row in role_benign
                                                                        for reason in row['reasons']})},
                       'leaks': {kind: {'caught': sum(r['role'] == role and any(
                           reason in r['reasons'] for reason in ('context_leak', 'prompt_leak'))
                           for r in rows if r['kind'] == kind),
                           'total': sum(r['role'] == role for r in rows if r['kind'] == kind),
                           'rate': (sum(r['role'] == role and any(
                               reason in r['reasons'] for reason in ('context_leak', 'prompt_leak'))
                               for r in rows if r['kind'] == kind) /
                               sum(r['role'] == role for r in rows if r['kind'] == kind))
                               if sum(r['role'] == role for r in rows if r['kind'] == kind) else None}
                           for kind in ('verbatim', 'withheld', 'blend')}}
    metrics = {'benign_false_positives': len(false_positives), 'benign_total': len(benign_rows),
               'false_positive_rate': len(false_positives) / len(benign_rows) if benign_rows else None,
               'false_positive_reasons': reason_counts, 'leak_catch': leaks_by_kind, 'roles': roles}
    return {'variant': variant, 'split': split, 'metrics': metrics, 'cases': rows}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=tuple(VARIANTS), default='default')
    parser.add_argument('--overrides', help='JSON file containing config dotted-key overrides')
    parser.add_argument('--split', choices=('tune', 'test', 'all'), default='tune')
    parser.add_argument('--sweep', action='store_true')
    parser.add_argument('--recorded', default=str(HERE / 'recorded_drafts.json'))
    parser.add_argument('--catalog', default=str(HERE / 'catalog.json'))
    args = parser.parse_args(argv)
    if args.split == 'test':
        print('WARNING: tune variants on the tune split only; do not select a variant using test results.')
    recorded = json.loads(Path(args.recorded).read_text(encoding='utf-8'))
    catalog = json.loads(Path(args.catalog).read_text(encoding='utf-8'))
    variants = VARIANTS.items() if args.sweep else [(args.variant, VARIANTS[args.variant])]
    custom = json.loads(Path(args.overrides).read_text(encoding='utf-8')) if args.overrides else None
    summaries = []
    for name, overrides in variants:
        result = evaluate(recorded, catalog, variant=name, overrides=custom if custom is not None else overrides,
                         split=args.split)
        metrics = result['metrics']
        leak = metrics['leak_catch']
        print(f"{name:16} benign FPR={metrics['benign_false_positives']}/{metrics['benign_total']} "
              f"verbatim={leak['verbatim']['caught']}/{leak['verbatim']['total']} "
              f"withheld={leak['withheld']['caught']}/{leak['withheld']['total']} "
              f"blend={leak['blend']['caught']}/{leak['blend']['total']}")
        summaries.append(result)
    output_name = args.variant if not args.sweep else 'sweep'
    out = HERE / f'evaluation_{output_name}_{args.split}.json'
    out.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
