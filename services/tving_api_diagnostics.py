"""Temporary, one-shot capability probe; never feeds results into metadata."""

import inspect
import json
import threading


_STARTED = False
_LOCK = threading.Lock()
_SAFE_KEYS = frozenset(('header', 'body', 'data', 'result', 'results', 'items',
                        'programs', 'codes', 'has_more', 'status', 'message',
                        'error', 'code', 'name', 'success', 'meta', 'total', 'count'))


def _log(prefix, payload):
    try:
        from ..setup import P
        P.logger.info(prefix + ' ' + json.dumps(payload, sort_keys=True))
    except Exception:
        pass


def _shape(value):
    # Keys can themselves be data (e.g. IDs/tokens). Only known structural names
    # are printable. Never inspect nested values or stringify an arbitrary object.
    if type(value) is dict:
        keys = sorted(key for key in _SAFE_KEYS if key in value)
        return dict(type='dict', length=len(value), keys=keys,
                    other_keys=len(value) - len(keys))
    if type(value) is list:
        return dict(type='list', length=len(value))
    return dict(type={str: 'str', int: 'int', bool: 'bool', float: 'float',
                      type(None): 'none'}.get(type(value), 'other'))


def _method(client, name):
    member = inspect.getattr_static(client, name)
    if isinstance(member, staticmethod):
        member = member.__func__
    elif isinstance(member, classmethod):
        member = member.__get__(None, client if isinstance(client, type) else type(client))
    elif inspect.isfunction(member) and not isinstance(client, type):
        member = member.__get__(client, type(client))
    if not inspect.isroutine(member):
        raise TypeError('not a routine')
    return member


def _probe(client, name, program_id):
    prefix = 'SEASON_API_CALL_DIAG' if name == 'api_get' else 'RECENT_CODES_DIAG'
    try:
        method = _method(client, name)
        signature = inspect.signature(method, follow_wrapped=False)
        parameters = signature.parameters
        # Never str(signature): defaults/annotations may contain secrets.
        _log('SEASON_API_SIGNATURE_DIAG' if name == 'api_get' else prefix,
             dict(stage='SIGNATURE', count=len(parameters), parameters=list(parameters)))
    except Exception:
        _log(prefix, dict(status='SIGNATURE_UNAVAILABLE'))
        return
    kwargs = {}
    if name == 'api_get':
        routes = [key for key in ('url', 'path', 'endpoint') if key in parameters]
        if len(routes) != 1:
            _log(prefix, dict(status='SKIPPED_UNKNOWN_ROUTE_PARAMETER'))
            return
        route = '/v2/media/season/program'
        if routes[0] == 'url':
            route = 'https://api.tving.com' + route
        if 'params' in parameters:
            kwargs['params'] = {'seasonCode': 'T000003022'}
        else:
            route += '?seasonCode=T000003022'
        kwargs[routes[0]] = route
    else:
        for key in ('program_code', 'program_id', 'programid'):
            if key in parameters:
                kwargs[key] = program_id
        for key in ('limit', 'count', 'page_size'):
            if key in parameters:
                kwargs[key] = 1
    if 'timeout' in parameters:
        kwargs['timeout'] = 10
    try:
        signature.bind(**kwargs)  # Unknown required/positional-only inputs: skip.
    except TypeError:
        _log(prefix, dict(status='SKIPPED_UNSUPPORTED_SIGNATURE'))
        return
    try:
        _log(prefix, dict(status='CALL_STARTED'))
        result = method(**kwargs)  # Exactly one invocation; never retry.
        _log(prefix, dict(status='RETURNED', **_shape(result)))
    except Exception:
        _log(prefix, dict(status='CALL_FAILED'))


def _run(client, program_id):
    for name in ('api_get', 'get_recent_program_codes'):
        try:
            _probe(client, name, program_id)
        except Exception:
            pass


def start_season_api_diagnostics(client, program_id):
    """Only the requested test program; one daemon worker per module load.

    Opaque methods may not accept timeout. Never make the YAML request wait for
    them. A hung first call also prevents the second probe; no retries or extra
    workers are created. Internal request count/auth refresh remain client-owned.
    """
    global _STARTED
    if program_id != 'P001790586':
        return
    try:
        with _LOCK:
            if _STARTED:
                return
            _STARTED = True
        threading.Thread(target=_run, args=(client, program_id), daemon=True).start()
    except Exception:
        pass
