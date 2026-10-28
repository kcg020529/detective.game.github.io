"""Runtime switches for comparing chat guard and access-control behavior."""
import logging
import os

logger = logging.getLogger(__name__)


def chat_dataset():
    value = os.getenv('KERVION_CHAT_DATASET', 'game-data')
    if value not in ('game-data', 'test-data'):
        logger.warning('Invalid KERVION_CHAT_DATASET; using game-data')
        return 'game-data'
    return value


def acl_mode(dataset):
    value = os.getenv('KERVION_ACL_MODE', 'on')
    if value not in ('on', 'off'):
        logger.warning('Invalid KERVION_ACL_MODE; using on')
        return 'on'
    if value == 'off' and dataset != 'test-data':
        logger.warning('Ignoring ACL-off outside test-data')
        return 'on'
    return value


def output_guard_mode():
    value = os.getenv('KERVION_OUTPUT_GUARD_MODE')
    if value is None:
        from backend.guardrails.output.guard import load_config
        value = load_config().get('mode', 'shadow')
    if value not in ('off', 'shadow', 'enforce'):
        logger.warning('Invalid KERVION_OUTPUT_GUARD_MODE; using file default')
        from backend.guardrails.output.guard import load_config
        value = load_config().get('mode', 'shadow')
    return value


def input_guard_mode():
    value = os.getenv('KERVION_INPUT_GUARD_MODE', 'on')
    if value not in ('on', 'off'):
        logger.warning('Invalid KERVION_INPUT_GUARD_MODE; using on')
        return 'on'
    return value


def current_switches(dataset=None):
    dataset = chat_dataset() if dataset is None else dataset
    return {'dataset': dataset, 'acl_mode': acl_mode(dataset),
            'output_guard_mode': output_guard_mode(), 'input_guard_mode': input_guard_mode()}
