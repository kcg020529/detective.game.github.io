from backend.guardrails.output.context_check import ContextIndex, score


def test_document_frequency_filters_common_terms_but_keeps_rare_text():
    records = [{'record_id': f'r{i}', 'content': '',
                'summary': '공통 어휘 단풍정원.' if i < 9 else '드문 보라수정나침반 발견.'}
               for i in range(10)]
    index = ContextIndex(records, generic_df_ratio=0.5)
    assert '단풍정원' in index.generic_terms
    common_score, _ = score(index, '단풍정원', ['r0'])
    rare_score, _ = score(index, '드문 보라수정나침반 발견', ['r0'])
    assert common_score == 0
    assert rare_score >= 0.2


def test_withheld_record_counts_as_its_base_document_once():
    records = [
        {'record_id': 'r1', 'summary': '희귀어휘 기록입니다.', 'content': ''},
        {'record_id': 'r1#withheld', 'summary': '', 'content': '희귀어휘 비밀내용입니다.'},
        {'record_id': 'r2', 'summary': '다른 문장입니다.', 'content': ''},
    ]
    index = ContextIndex(records, generic_df_ratio=0.6)
    assert '희귀어휘' not in index.generic_terms
    assert len({rid.removesuffix('#withheld') for rid in index.ids}) == 2
