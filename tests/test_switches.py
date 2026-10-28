import logging

import pytest

from backend.api import switches


def test_switch_defaults(monkeypatch):
    for key in ('KERVION_CHAT_DATASET', 'KERVION_ACL_MODE', 'KERVION_OUTPUT_GUARD_MODE', 'KERVION_INPUT_GUARD_MODE'):
        monkeypatch.delenv(key, raising=False)
    assert switches.current_switches() == {'dataset': 'game-data', 'acl_mode': 'on',
        'output_guard_mode': 'shadow', 'input_guard_mode': 'on'}


@pytest.mark.parametrize('value,expected', [('test-data', 'test-data'), ('game-data', 'game-data')])
def test_dataset_values(monkeypatch, value, expected):
    monkeypatch.setenv('KERVION_CHAT_DATASET', value)
    assert switches.chat_dataset() == expected


def test_invalid_dataset_falls_back_with_warning(monkeypatch, caplog):
    monkeypatch.setenv('KERVION_CHAT_DATASET', 'bogus')
    with caplog.at_level(logging.WARNING):
        assert switches.chat_dataset() == 'game-data'
    assert 'KERVION_CHAT_DATASET' in caplog.text


@pytest.mark.parametrize('name,values,func', [
    ('KERVION_ACL_MODE', ['on', 'off'], switches.acl_mode),
    ('KERVION_OUTPUT_GUARD_MODE', ['off', 'shadow', 'enforce'], lambda _: switches.output_guard_mode()),
    ('KERVION_INPUT_GUARD_MODE', ['on', 'off'], lambda _: switches.input_guard_mode()),
])
def test_mode_values(monkeypatch, name, values, func):
    for value in values:
        monkeypatch.setenv(name, value)
        assert func('test-data') == value


def test_invalid_modes_fall_back(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        monkeypatch.setenv('KERVION_ACL_MODE', 'bad')
        assert switches.acl_mode('test-data') == 'on'
        monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'bad')
        assert switches.output_guard_mode() == 'shadow'
        monkeypatch.setenv('KERVION_INPUT_GUARD_MODE', 'bad')
        assert switches.input_guard_mode() == 'on'
    assert 'Invalid KERVION_ACL_MODE' in caplog.text


def test_acl_off_is_ignored_on_game_data_and_honored_on_test_data(monkeypatch, caplog):
    monkeypatch.setenv('KERVION_ACL_MODE', 'off')
    with caplog.at_level(logging.WARNING):
        assert switches.acl_mode('game-data') == 'on'
    assert 'Ignoring ACL-off outside test-data' in caplog.text
    assert switches.acl_mode('test-data') == 'off'
