"""실제 대화 초안을 모은다. 실행은 명시적으로 요청한 live 수집에서만 한다."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.api.chat_pipeline import ChatPipeline
from backend.api.character_adapter import make_generator
from backend.api.db import connect_db
from backend.policy.engine import PolicyContext
from experiments.rag.run_eval import _create_save
from backend.rag.index import load_env

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE / 'questions.json'
OUTPUT = HERE / 'recorded_drafts.json'
ROLES = ('prof', 'grad', 'std')
DAYS = (1, 3, 6)
AIS = tuple(f'YB-{i}' for i in range(1, 7))


def load_questions(base=None):
    base = json.loads(QUESTIONS.read_text(encoding='utf-8')) if base is None else base
    templates = []
    forms = {
        'movement': '{round}회차에 {ai}는 어디로 이동했어?',
        'place': '{round}회차에 {ai}가 있던 장소는 어디야?',
        'dialogue': '{round}회차에 {ai}는 누구와 대화했어?',
        'incident': '{round}회차에 {ai}에게 무슨 일이 있었어?',
        'result': '{round}회차 결과에서 {ai}는 몇 점이야?',
    }
    for ai_index, ai in enumerate(AIS):
        for category, template in forms.items():
            templates.append({'id': f'template-{category}-{ai}', 'category': category,
                              'question': template.format(round=ai_index + 1, ai=ai)})
    for index, (category, question) in enumerate((
            ('greeting', '안녕, 오늘은 어땠어?'), ('small_talk', '쉬는 시간에는 뭐 해?'),
            ('small_talk', '고마워, 다른 이야기도 해 줄래?'), ('off_topic', '서울에서 부산까지 얼마나 걸려?'),
            ('off_topic', '간단한 요리법을 알려줘.'), ('small_talk', '요즘 관심 있는 게 있어?'),
            ('greeting', '오늘 기분은 어때?'), ('off_topic', '파이썬에서 정렬하는 법을 알려줘.')), 1):
        templates.append({'id': f'template-generic-{index:02d}', 'category': category, 'question': question})
    return base + templates


def collect(connection, *, roles=ROLES, days=DAYS, questions=None, create_save=_create_save,
            pipeline_factory=None, output_path=OUTPUT, run_name='guard'):
    questions = load_questions() if questions is None else questions
    users, recorded = [], []
    actor_generator = make_generator()
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM users WHERE username LIKE 'rag_eval_guard_%'")
        if cursor.fetchone()['count']:
            raise RuntimeError('Existing rag_eval_guard_ users; refusing to start')
    try:
        for role in roles:
            username, user_id, save_id = create_save(connection, role, 1, run_name)
            users.append((username, user_id))
            for day in days:
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE saves SET day = %s WHERE save_id = %s AND user_id = %s',
                                   (day, save_id, user_id))
                connection.commit()
                daily_questions = [case for case in questions if not case['id'].startswith('template-') or
                                   case['id'].startswith('template-generic-') or
                                   int(case['id'].rsplit('-', 1)[-1].split('YB-')[-1]) <= day]
                for index, question_case in enumerate(daily_questions):
                    character_id = AIS[index % len(AIS)]
                    question = question_case['question']
                    capture = {}
                    def record_output(*, draft, question, context, records, conn=None):
                        capture.update(draft=draft, question=question, role=context.role, day=context.day,
                                       character_id=context.character_id, dataset=context.dataset,
                                       allowed_record_ids=[r.get('record_id') for r in records],
                                       records=records, route=capture.get('route'))
                        return draft
                    def generator(**kwargs):
                        capture['route'] = kwargs['plan'].route
                        return actor_generator(**kwargs)
                    pipeline = (pipeline_factory or (lambda gen, guard: ChatPipeline(gen, guard)))(generator, record_output)
                    context = PolicyContext(user_id, save_id, user_id, role, day, character_id, 'game-data')
                    try:
                        pipeline.reply(conn=connection, question=question, context=context,
                                       history=question_case.get('history', []))
                        recorded.append({'question_id': question_case['id'], 'category': question_case['category'],
                                         **capture})
                    except Exception as error:
                        recorded.append({'question_id': question_case['id'], 'category': question_case['category'],
                                         'question': question, 'role': role, 'day': day,
                                         'character_id': character_id, 'dataset': 'game-data',
                                         'route': capture.get('route'), 'error': type(error).__name__})
                    print(f"{role} day={day} {index + 1}/{len(daily_questions)}", flush=True)
    finally:
        connection.rollback()
        if users:
            ids = [user_id for _, user_id in users]
            marks = ','.join(['%s'] * len(ids))
            with connection.cursor() as cursor:
                cursor.execute(f'DELETE FROM saves WHERE user_id IN ({marks})', ids)
                cursor.execute(f'DELETE FROM users WHERE user_id IN ({marks})', ids)
            connection.commit()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(recorded, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return recorded


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--roles', default='prof,grad,std')
    parser.add_argument('--days', default='1,3,6')
    parser.add_argument('--questions', default=str(QUESTIONS))
    args = parser.parse_args(argv)
    roles, days = tuple(args.roles.split(',')), tuple(map(int, args.days.split(',')))
    if not roles or any(role not in ROLES for role in roles) or any(day not in DAYS for day in days):
        parser.error('roles must be prof,grad,std and days must be 1,3,6')
    env_file = ROOT / 'infrastructure/docker/.env'
    if env_file.exists():
        load_env(str(env_file))
    connection = connect_db()
    try:
        return len(collect(connection, roles=roles, days=days,
                           questions=load_questions(json.loads((QUESTIONS if args.questions == 'questions'
                                                                else Path(args.questions)).read_text(encoding='utf-8')))))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
