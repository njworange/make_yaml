from ..providers.legacy_registry import get_direct_command_prefix, get_ottcode_class, get_provider_name
from ..setup import P
from .code_service import sort_code


def resolve_search_parts(parts):
    ottcode_class = get_ottcode_class()
    user_order = P.ModelSetting.get_list('ftv_first_order', ',')
    if len(parts) == 1:
        ottcode = ottcode_class(parts[0].strip())
    elif len(parts) == 2:
        ottcode = ottcode_class(parts[0].strip(), parts[1].strip())
    else:
        return None, None
    ottcode_list = ottcode.get_ott_code()
    return sort_code(user_order, ottcode_list), ottcode


def resolve_search_keyword(keyword_text):
    return resolve_search_parts(keyword_text.split('|'))


def build_direct_code(command, arg1):
    prefix = get_direct_command_prefix(command)
    if prefix is None:
        return ''
    return prefix + arg1


def get_site_name(prefix):
    return get_provider_name(prefix)
