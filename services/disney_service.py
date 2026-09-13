from flask import jsonify

from ..providers.disney_resolver import is_disney_entity_code, resolve_input
from .disney_provider import disney_entity_input, uses_disney_public_route


def handle_disney_command(arg1, arg2):
    # Entity pages now contain their own episode metadata. Do not resolve them
    # through title search into a potentially different legacy series identity.
    if uses_disney_public_route(arg1):
        if not disney_entity_input(arg1)[0]:
            return None, jsonify({'ret': 'fail', 'msg': '디즈니 entity 입력 형식 오류'})
        return 'FD' + arg1, None
    needs_redirect = 'disneyplus.com' in arg1 or arg1.startswith('entity-')
    unresolved_before = is_disney_entity_code(arg1)
    if not needs_redirect and unresolved_before:
        needs_redirect = True
    if not needs_redirect:
        return 'FD' + arg1, None

    resolved = resolve_input(arg1)
    unresolved_after = is_disney_entity_code(resolved)
    if unresolved_after:
        if arg2 == 'test':
            return None, jsonify({'ret':'fail', 'msg':'디즈니 시리즈 코드 확인 실패', 'json': []})
        return None, jsonify({'msg':'검색 실패', 'ret':'fail'})
    return 'FD' + resolved, None
