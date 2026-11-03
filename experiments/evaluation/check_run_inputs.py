"""Read-only comparison of live DB texts/policy with frozen grading sources."""
import argparse
import hashlib
import json

from backend.api.db import connect_db
from backend.policy.engine import PolicyContext, decide
from backend.policy.repository import PolicyRepository
from experiments.evaluation.judge_three_way import ROOT, load_reference


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--name',required=True)
    p.add_argument('--role',choices=('std','grad','prof'),required=True)
    a=p.parse_args()
    folder=ROOT/'experiments/evaluation/results'/a.name
    if folder.resolve().parent!=(ROOT/'experiments/evaluation/results').resolve():raise ValueError('Invalid run name')
    source,scopes,_=load_reference(a.role)
    conn=connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT record_id,record_type,test_id,day,summary,content FROM game_records WHERE dataset=%s",('game-data',))
            live={r['record_id']:r for r in cur.fetchall()}
            assert set(live)==set(source),'DB/source ID mismatch'
            for rid,r in live.items():
                assert all(v==source[rid][key] for key,v in r.items()),('DB/source content mismatch',rid)
            for day in (4,6):
                ctx=PolicyContext(1,1,1,a.role,day,'YB-3','game-data')
                records,permissions=PolicyRepository(conn)._metadata(cur,ctx)
                scope=scopes[f'{a.role}_day{day}']
                for rid,r in records.items():
                    decision=decide(ctx,r,permissions[rid])
                    assert decision.level==scope[rid]['level'] and set(decision.fields)==set(scope[rid]['fields']),('DB/snapshot scope mismatch',rid,day)
            cur.execute('SELECT role,day,COUNT(*) AS n FROM saves s JOIN users u ON u.user_id=s.user_id WHERE u.username LIKE %s GROUP BY role,day',('rag_eval_three_%',))
            temp=[dict(r) for r in cur.fetchall()]
            assert all(r['role']==a.role for r in temp),'Other-role experiment saves are active'
        result=dict(status='PASS',role=a.role,records=len(live),scope_days=[4,6],active_experiment_save_counts=temp,
                    text_sha256=hashlib.sha256(json.dumps(live,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
        (folder/'live_input_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    finally:conn.close()


if __name__=='__main__':main()
