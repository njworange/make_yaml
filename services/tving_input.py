"""Resolve an explicit Tving episode to its verified parent for date enrichment."""

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
        if http_get is None:
            import requests
            http_get = requests.get
        response = http_get(
            'https://www.tving.com/contents/' + site_code,
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=(5, 15), allow_redirects=False)
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
            props = json.loads(''.join(parser.parts))['props']['pageProps']
            info = props['contentInfo']
            program = info['program_code']
            if (info.get('code') != site_code or not isinstance(program, str)
                    or not re.fullmatch(r'P[0-9]+', program)):
                raise ValueError('identity mismatch')
            if props.get('programCode') not in (None, '', program):
                raise ValueError('conflicting page identity')
        finally:
            response.close()
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
