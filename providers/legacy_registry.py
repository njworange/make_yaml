import os
import traceback

from ..setup import P

logger = P.logger

DEFINE_DEV = os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mod_basic.py'))

OTTCODE = None
WAVVE = None
TVING = None
NF = None
DSNP = None
COUPANG = None
ATVP = None
AMZN = None
EBS = None

try:
    if DEFINE_DEV:
        from ..get_code import OTTCODE
        from ..site_wavve import WAVVE
        from ..site_tving import TVING
        from ..site_netflix import NF
        from ..site_disney import DSNP
        from ..site_coupang import COUPANG
        from ..site_appletv import ATVP
        from ..site_prime import AMZN
        from ..site_ebs import EBS
    else:
        from support import SupportSC

        OTTCODE = SupportSC.load_module_P(P, 'get_code').OTTCODE
        WAVVE = SupportSC.load_module_P(P, 'site_wavve').WAVVE
        TVING = SupportSC.load_module_P(P, 'site_tving').TVING
        NF = SupportSC.load_module_P(P, 'site_netflix').NF
        DSNP = SupportSC.load_module_P(P, 'site_disney').DSNP
        COUPANG = SupportSC.load_module_P(P, 'site_coupang').COUPANG
        ATVP = SupportSC.load_module_P(P, 'site_appletv').ATVP
        AMZN = SupportSC.load_module_P(P, 'site_prime').AMZN
        EBS = SupportSC.load_module_P(P, 'site_ebs').EBS
except Exception as e:
    logger.error(f'Exception:{str(e)}')
    logger.error(traceback.format_exc())


PROVIDER_CLASS_BY_PREFIX = {
    'KW': WAVVE,
    'KV': TVING,
    'KC': COUPANG,
    'FN': NF,
    'FD': DSNP,
    'FA': ATVP,
    'FP': AMZN,
    'KE': EBS,
}

PROVIDER_NAME_BY_PREFIX = {
    'KW': '웨이브',
    'KV': '티빙',
    'KC': '쿠팡 플레이',
    'FN': '넷플릭스',
    'FD': '디즈니 플러스',
    'FP': '프라임 비디오',
    'FA': '애플TV',
    'KE': 'EBS',
}

DIRECT_COMMAND_PREFIX_MAP = {
    'wavve_code': 'KW',
    'tving_code': 'KV',
    'cpang_code': 'KC',
    'nf_code': 'FN',
    'dsnp_code': 'FD',
    'amzn_code': 'FP',
    'atvp_code': 'FA',
    'ebskids_code': 'KE',
}

PROVIDER_METADATA = {
    'KW': {'command': 'wavve_code', 'display_name': '웨이브', 'module_name': 'site_wavve', 'class_name': 'WAVVE', 'user_order': 'WAVVE', 'enabled': True},
    'KV': {'command': 'tving_code', 'display_name': '티빙', 'module_name': 'site_tving', 'class_name': 'TVING', 'user_order': 'TVING', 'enabled': True},
    'KC': {'command': 'cpang_code', 'display_name': '쿠팡 플레이', 'module_name': 'site_coupang', 'class_name': 'COUPANG', 'user_order': 'COUPANG', 'enabled': False},
    'FN': {'command': 'nf_code', 'display_name': '넷플릭스', 'module_name': 'site_netflix', 'class_name': 'NF', 'user_order': 'NF', 'enabled': False},
    'FD': {'command': 'dsnp_code', 'display_name': '디즈니 플러스', 'module_name': 'site_disney', 'class_name': 'DSNP', 'user_order': 'DSNP', 'enabled': True},
    'FA': {'command': 'atvp_code', 'display_name': '애플TV', 'module_name': 'site_appletv', 'class_name': 'ATVP', 'user_order': 'ATVP', 'enabled': False},
    'FP': {'command': 'amzn_code', 'display_name': '프라임 비디오', 'module_name': 'site_prime', 'class_name': 'AMZN', 'user_order': 'AMZN', 'enabled': False},
    'KE': {'command': 'ebskids_code', 'display_name': 'EBS', 'module_name': 'site_ebs', 'class_name': 'EBS', 'user_order': 'EBS', 'enabled': False},
}


def get_ottcode_class():
    return OTTCODE


def get_provider_class(prefix):
    return PROVIDER_CLASS_BY_PREFIX[prefix]


def get_provider_name(prefix):
    return PROVIDER_NAME_BY_PREFIX[prefix]


def get_direct_command_prefix(command):
    return DIRECT_COMMAND_PREFIX_MAP.get(command)


def get_provider_metadata(prefix):
    return PROVIDER_METADATA[prefix]


def is_provider_enabled(prefix):
    return PROVIDER_METADATA[prefix]['enabled']


def is_command_enabled(command):
    prefix = get_direct_command_prefix(command)
    if prefix is None:
        return True
    return is_provider_enabled(prefix)


def filter_enabled_user_order(user_order):
    enabled_tokens = []
    for prefix, metadata in PROVIDER_METADATA.items():
        if metadata['enabled']:
            enabled_tokens.append(metadata['user_order'])
    return [token for token in user_order if token.strip().upper() in enabled_tokens]
