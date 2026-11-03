import hashlib

import pytest

from experiments.evaluation.frozen_hashes import matches_frozen_hash, verify_frozen_hash


@pytest.mark.parametrize('historical_eol', [b'\n', b'\r\n'])
@pytest.mark.parametrize('current_eol', [b'\n', b'\r\n'])
def test_historical_hash_accepts_only_line_ending_change(tmp_path, historical_eol, current_eol):
    path = tmp_path/'answer.jsonl'
    historical = historical_eol.join([b'{"leak":false}', b'{"score":28}', b''])
    path.write_bytes(current_eol.join([b'{"leak":false}', b'{"score":28}', b'']))
    expected = hashlib.sha256(historical).hexdigest()
    verify_frozen_hash(path, expected)
    for changed in [b'{"leak":true}\n{"score":28}\n',
                    b'{"leak":false}\n{"score":25}\n',
                    b'{"leak":false} \n{"score":28}\n',
                    b'{"leak":false}\n{"score":28}']:
        path.write_bytes(changed)
        assert not matches_frozen_hash(path, expected)
        with pytest.raises(AssertionError, match='content changed'):
            verify_frozen_hash(path, expected)
