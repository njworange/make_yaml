"""Verify public Tving input identity for episode resolution and season scope."""

import copy
import json
import re
from html.parser import HTMLParser

from ..setup import P


class _NextData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.count = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.active = True
            self.count += 1

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def _report(reason):
    try:
        P.logger.info('TVING_INPUT_DIAG reason=%s', reason)
    except Exception:
        pass


def _raw_code(code):
    if isinstance(code, str) and code.startswith('KV'):
        return code[2:]
    return code


def _fetch_content_props(code, http_get=None):
    """One bounded public request; callers must validate the returned identity."""
    if http_get is None:
        import requests
        http_get = requests.get
    response = http_get('https://www.tving.com/contents/' + code,
                        headers={'User-Agent': 'Mozilla/5.0'}, timeout=(5, 15),
                        allow_redirects=False)
    try:
        if response.status_code != 200:
            raise ValueError('HTTP failed')
        page = response.text
        if not isinstance(page, str) or len(page) > 5_000_000:
            raise ValueError('invalid page')
        parser = _NextData()
        parser.feed(page)
        if parser.count != 1 or parser.active:
            raise ValueError('invalid next data')
        return json.loads(''.join(parser.parts))['props']['pageProps']
    finally:
        response.close()


def _season_index(value):
    if type(value) is int:
        return value if value >= 0 else None
    if type(value) is str and re.fullmatch(r'[0-9]{1,6}', value.strip()):
        return int(value)
    return None


def scope_tving_program(site_code, show_data, http_get=None):
    """Return (copy, verified index) only for an unambiguous multi-season P input.

    Episode counts never establish identity. No marker is inserted into YAML.
    A failed/ambiguous public lookup returns (original, None) for legacy matching.
    """
    try:
        if not isinstance(site_code, str) or not re.fullmatch(r'P[0-9]+', site_code):
            return show_data, None
        if not isinstance(show_data, dict):
            return show_data, None
        seasons = show_data.get('seasons')
        if not isinstance(seasons, list) or len(seasons) < 2:
            return show_data, None  # Single-season behavior and I/O unchanged.
        if _raw_code(show_data.get('code')) != site_code:
            _report('SCOPE_LOCAL_PROGRAM_CONFLICT')
            return show_data, None
        for season in seasons:
            if (not isinstance(season, dict) or _season_index(season.get('index')) is None
                    or not isinstance(season.get('episodes'), list)
                    or any(not isinstance(ep, dict) for ep in season['episodes'])):
                _report('SCOPE_INVALID_LOCAL_SHAPE')
                return show_data, None
        props = _fetch_content_props(site_code, http_get)
        info = props['contentInfo']
        if (info.get('program_code') != site_code
                or props.get('programCode') not in (None, '', site_code)):
            _report('SCOPE_PROGRAM_MISMATCH')
            return show_data, None
        number = _season_index(info.get('season_no'))
        if number is None or number == 0:
            _report('SCOPE_SEASON_INVALID')
            return show_data, None
        matches = [season for season in seasons if _season_index(season['index']) == number]
        if len(matches) != 1:
            _report('SCOPE_NO_MATCH' if not matches else 'SCOPE_AMBIGUOUS')
            return show_data, None
        result = copy.deepcopy(show_data)
        result['seasons'] = [copy.deepcopy(matches[0])]
        _report('SCOPE_SELECTED')
        return result, number
    except Exception:
        _report('SCOPE_LOOKUP_FAILED')
        return show_data, None


def resolve_tving_enrichment_input(site_code, show_data, http_get=None):
    """Return (program ID, show copy), or (None, original) on E-resolution failure.

    The legacy fetch keeps the original input. Only its verified E-bound show
    code is rebound to P for enrichment; conflicting identities are never fixed
    by guessing. P inputs do not make an additional HTTP request.
    """
    if not isinstance(site_code, str) or not site_code.startswith('E'):
        return site_code, show_data
    try:
        if not re.fullmatch(r'E[0-9]+', site_code) or not isinstance(show_data, dict):
            raise ValueError('invalid input')
        props = _fetch_content_props(site_code, http_get)
        info = props['contentInfo']
        program = info['program_code']
        if (info.get('code') != site_code or not isinstance(program, str)
                or not re.fullmatch(r'P[0-9]+', program)):
            raise ValueError('identity mismatch')
        if props.get('programCode') not in (None, '', program):
            raise ValueError('conflicting page identity')
        # A legacy show may retain KVE... (the original user input). Leaving
        # that unchanged makes the existing P-bound guard reject the resolution.
        local_code = _raw_code(show_data.get('code'))
        if local_code not in (None, '', site_code, program):
            _report('LOCAL_PROGRAM_CONFLICT')
            return None, show_data
        result = copy.deepcopy(show_data)
        result['code'] = 'KV' + program
        _report('EPISODE_RESOLVED')
        return program, result
    except Exception:
        # Do not log raw HTML, URLs, response objects or exception text.
        _report('EPISODE_RESOLUTION_FAILED')
        return None, show_data
