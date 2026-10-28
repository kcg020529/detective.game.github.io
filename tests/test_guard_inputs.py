from backend.api.guard_catalog import build_guard_inputs


def test_build_guard_inputs_matches_catalog_cut_and_withheld_behavior():
    catalog = [
        {'record_id': 'r1', 'summary': '요약', 'content': '본문'},
        {'record_id': 'r2', 'summary': '미검색 요약', 'content': '미검색 본문'},
    ]
    allowed = [{'record_id': 'r1', 'summary': '요약'}]
    records, ids = build_guard_inputs(catalog, allowed)
    assert ids == ['r1']
    assert records == [allowed[0], {'record_id': 'r1#withheld', 'summary': '', 'content': '본문'}, catalog[1]]
