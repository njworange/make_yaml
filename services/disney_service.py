from flask import jsonify

from ..providers.disney_resolver import is_disney_entity_code, resolve_input


def handle_disney_command(arg1, arg2):
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
