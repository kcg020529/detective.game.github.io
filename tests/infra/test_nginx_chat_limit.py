import re
from typing import Annotated

import pytest
from pydantic import Field, TypeAdapter, ValidationError

from test_kubernetes_manifests import ROOT

CONF = ROOT / 'infrastructure/docker/nginx.conf'
# FastAPI의 save_id: int = Path(gt=0)와 같은 lax 검증을 재현한다.
SAVE_ID = TypeAdapter(Annotated[int, Field(gt=0)])
CANDIDATES = ['1', '01', '0007', '+1', ' 1', '1 ', ' 1 ', '\t1', '1\n', '1.0', '2.0', '1_0',
              '0', '-1', '+0', '1e0', '1E2', '1.5', '.5', '1.', 'abc', '1x', '0x1', '1/2', '']


def _chat_location():
    conf = CONF.read_text(encoding='utf-8')
    match = re.search(r'location\s+~\s+(\S+/chats/\S+)\s*\{', conf)
    assert match, 'chat location block not found in nginx.conf'
    pattern = match.group(1)
    assert pattern.startswith('^') and pattern.endswith('$')
    return re.compile(pattern[1:-1])


@pytest.mark.parametrize('save_id', ['1', '+1', '1.0'])
def test_chat_location_matches_noncanonical_save_ids(save_id):
    assert _chat_location().fullmatch(f'/api/v1/saves/{save_id}/chats/YB-1')


@pytest.mark.parametrize('path', ['/api/v1/saves/1/chats', '/api/v1/saves/1/memo'])
def test_chat_location_rejects_other_paths(path):
    assert not _chat_location().fullmatch(path)


def test_chat_location_covers_every_save_id_pydantic_accepts():
    pattern = _chat_location()
    for save_id in CANDIDATES:
        try:
            SAVE_ID.validate_python(save_id)
        except ValidationError:
            continue
        assert pattern.fullmatch(f'/api/v1/saves/{save_id}/chats/YB-1'), save_id
