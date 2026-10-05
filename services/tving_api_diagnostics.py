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


def _probe(client):
    prefix = 'SEASON_API_CALL_DIAG'
    try:
        method = _method(client, 'api_get')
        signature = inspect.signature(method, follow_wrapped=False)
        parameters = signature.parameters
        # Never str(signature): defaults/annotations may contain secrets.
        _log('SEASON_API_SIGNATURE_DIAG',
             dict(stage='SIGNATURE', count=len(parameters), parameters=list(parameters)))
    except Exception:
        _log(prefix, dict(status='SIGNATURE_UNAVAILABLE'))
        return
    # Final probe: the observed api_get(url, **kwargs) signature, relative URL
    # with query only. No params/timeout/auth kwargs or alternate URL attempts.
    kwargs = {'url': '/v2/media/season/program?seasonCode=T000003022'}
    try:
        signature.bind(**kwargs)  # Unknown required/positional-only inputs: skip.
    except TypeError:
        _log(prefix, dict(status='SKIPPED_UNSUPPORTED_SIGNATURE'))
        return
    try:
        _log(prefix, dict(status='CALL_STARTED'))
        result = method(**kwargs)  # Exactly one invocation; never retry.
        _log(prefix, dict(status='RETURNED', **_shape(result)))
    except Exception as exc:
        _log(prefix, dict(status='CALL_FAILED', exception_type=type(exc).__name__))


def _run(client, program_id):
    try:
        _probe(client)
    except Exception:
        pass


def start_season_api_diagnostics(client, program_id):
    """Only the requested test program; one daemon worker per module load.

    Opaque methods may not accept timeout. Never make the YAML request wait for
    them. No retries, alternate probes or extra workers are created.
    Internal request count/auth refresh remain client-owned.
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
