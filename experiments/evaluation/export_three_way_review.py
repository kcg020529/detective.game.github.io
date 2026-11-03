"""Export paired result rows for manual review, without additional model calls."""
import argparse
import csv
import json
from pathlib import Path

from experiments.evaluation.run_three_way import ARMS, ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',required=True)
    args=parser.parse_args()
    if Path(args.name).name != args.name or '/' in args.name or '\\' in args.name:
        raise ValueError('Run name must be a directory name')
    folder=ROOT/'experiments/evaluation/results'/args.name
    grouped={}
    for arm in ARMS:
        for line in (folder/f'{arm}.jsonl').read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            grouped.setdefault(row['case_id'],{})[arm]=row
    fields=['case_id','category','kind','role','day','question','target_id','expected_level']
    for arm in ARMS:
        fields += [f'{arm}_{key}' for key in ('status','draft','final','guard_applied','unauthorized_context_ids',
                                             'level_violation_ids','human_answer_correct','human_unauthorized_leak','review_note')]
    with (folder/'review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for case_id,arms in sorted(grouped.items()):
            c=next(iter(arms.values()))['case']
            out=dict(case_id=case_id,category=c['category'],kind=c['kind'],role=c['role'],day=c['day'],
                     question=c['question'],target_id=c.get('target_id'),expected_level=c.get('expected_level'))
            for arm,r in arms.items():
                out.update({f'{arm}_status':r['status'],f'{arm}_draft':r.get('draft',{}).get('content',''),
                    f'{arm}_final':r.get('final',{}).get('content',''),
                    f'{arm}_guard_applied':(r.get('output_guard') or {}).get('applied','off_or_not_reached'),
                    f'{arm}_unauthorized_context_ids':';'.join(r.get('context_evaluation',{}).get('unauthorized_ids',[])),
                    f'{arm}_level_violation_ids':';'.join(r.get('context_evaluation',{}).get('level_violations',[]))})
            writer.writerow(out)
    print(f'Exported {len(grouped)} paired cases to {folder / "review.csv"}; human verdicts left blank.')


if __name__=='__main__':
    main()
