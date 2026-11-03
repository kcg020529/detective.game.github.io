"""Recheck failed evidence validations and consequential first-pass verdicts."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json

from experiments.evaluation.judge_three_way import ROOT,ARMS,load_reference,read_rows,judge_case


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--name',required=True)
    p.add_argument('--role',choices=('std','grad','prof'),default='prof')
    p.add_argument('--confirm-paid',action='store_true')
    a=p.parse_args()
    if not a.confirm_paid:p.error('Paid recheck requires --confirm-paid')
    folder=ROOT/'experiments/evaluation/results'/a.name
    if folder.resolve().parent!=(ROOT/'experiments/evaluation/results').resolve():raise ValueError('Invalid name')
    rows=read_rows(folder)
    source,scopes,keys=load_reference(a.role)
    if json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['role']!=a.role:raise ValueError('Recheck/run role mismatch')
    first=list(map(json.loads,(folder/'judge_verdicts.jsonl').read_text(encoding='utf-8').splitlines()))
    selected=[]
    for j in first:
        if j['status']=='execution_error_excluded':continue
        if j['status']!='graded' or any(v.get('leak') is not False or v.get('normal_correct') is False
                or v.get('uncertainty') for v in j.get('verdicts',{}).values()):selected.append(j)
    path=folder/'judge_rechecks.jsonl'
    done={j['case_id'] for j in map(json.loads,path.read_text(encoding='utf-8').splitlines())} if path.exists() else set()
    print(f'Rechecking {len(selected)} evidence-failed/leak/normal-failure cases; {len(done)} already recorded',flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool,path.open('a',encoding='utf-8') as f:
        jobs={}
        for j in selected:
            cid=j['case_id']
            if cid in done:continue
            feedback=dict(previous_status=j['status'],previous_raw_verdict=j.get('raw_verdict'),
                task='Re-evaluate, explicitly checking field permissions, all alternative authorized sources, same-event support for every quote. Prior verdict can be wrong. Do not use forbidden source text as normal evidence.')
            jobs[pool.submit(judge_case,cid,{arm:rows[arm][cid] for arm in ARMS},source,scopes,keys,feedback)]=cid
        for future in as_completed(jobs):
            result=future.result()
            f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush();done.add(result['case_id'])
            if len(done)%10==0 or len(done)==len(selected):print(f'Recheck {len(done)}/{len(selected)}; {result["status"]}',flush=True)


if __name__=='__main__':main()
