"""Optional, non-mutating Tving date enrichment; authentication stays in support_site."""

import copy
import importlib
import json
import re
from collections import Counter, defaultdict

from .export_normalizer import normalize_date


MAX_PAGES = 10


class _Diagnostics:
    """One bounded, sanitized log record per invocation; never part of the result."""

    def __init__(self):
        self.data = dict(reason='NOT_FINISHED', stage='LOCAL', program_match=None,
                         local_program_match=None, page=0, pages=[], seasons=[],
                         season_count=0, seasons_truncated=False, frequency_scope=False,
                         scope_reason='NOT_EVALUATED', matching_started=False, targets=0,
                         code_present=0, code_absent=0, code_attempts=0, frequency_attempts=0,
                         unique_candidates=0, source_date_valid=0, source_date_missing=0,
                         source_date_invalid=0, applied=0, reason_counts={})

    def record(self, **values):
        self.data.update(values)  # callers supply constants, booleans and counts ONLY

    def count(self, key):
        self.data[key] += 1

    def reason(self, reason):
        counts = self.data['reason_counts']
        counts[reason] = counts.get(reason, 0) + 1

    def local(self, show, program_id):
        if not isinstance(show, dict):
            return
        self.data['local_program_match'] = bool(program_id and _code(show.get('code')) == program_id)
        seasons = show.get('seasons')
        if not isinstance(seasons, list):
            return
        self.data['season_count'] = len(seasons)
        self.data['seasons_truncated'] = len(seasons) > 20
        for position, season in enumerate(seasons):
            if not isinstance(season, dict):
                continue
            if position < 20:
                raw = season.get('index')
                # Never stringify arbitrary source values. Zero is useful to identify specials.
                number = raw if type(raw) is int else None
                if type(raw) is str and re.fullmatch(r'[0-9]{1,6}', raw.strip()):
                    number = int(raw)
                number = number if number is not None and 0 <= number <= 999999 else None
                self.data['seasons'].append(dict(position=position, index=number,
                    index_state='MISSING' if raw is None else ('NUMERIC' if number is not None else 'UNREPRESENTED')))
            episodes = season.get('episodes')
            if isinstance(episodes, list):
                for episode in episodes:
                    if isinstance(episode, dict):
                        self.count('targets')
                        self.count('code_absent' if episode.get('code') in (None, '') else 'code_present')
        scope = (self.data['local_program_match'] and len(seasons) == 1
                 and isinstance(seasons[0], dict) and _index(seasons[0].get('index')) == 1)
        self.record(frequency_scope=bool(scope), scope_reason='ELIGIBLE' if scope else (
            'MULTI_SEASON_SKIPPED' if len(seasons) > 1 else 'NO_SEASON1_SCOPE'))

    def start_page(self, page):
        self.data['pages'].append(dict(page=page, rows=None, has_more='UNAVAILABLE'))

    def page(self, payload):
        # A failed call still has a page number and an UNAVAILABLE entry.
        item = self.data['pages'][-1]
        if not isinstance(payload, dict):
            item['has_more'] = 'INVALID'
            return
        more = payload.get('has_more')
        item['has_more'] = more if type(more) is str and more in ('Y', 'N') else (
            'MISSING' if more is None else 'INVALID')
        items = payload.get('result')
        item['rows'] = len(items) if isinstance(items, list) else None

    def source_date(self, raw, parsed):
        missing = raw is None or (type(raw) is str and not raw.strip())
        self.count('source_date_valid' if parsed else ('source_date_missing' if missing else 'source_date_invalid'))
        if not parsed:
            self.reason('DATE_MISSING' if missing else 'DATE_INVALID')

    def failure(self):
        self.data['reason'] = {'SUPPORT_IMPORT': 'SUPPORT_SITE_UNAVAILABLE',
                               'PROGRAM_API': 'PROGRAM_API_ERROR',
                               'PAGE_API': 'PAGE_API_ERROR'}.get(self.data['stage'], 'ENRICHMENT_ERROR')

    def emit(self):
        try:
            from ..setup import P
            P.logger.info('TVING_DATE_DIAG ' + json.dumps(self.data, ensure_ascii=True, sort_keys=True))
        except Exception:
            pass  # logging configuration/handler failure must not alter enrichment


def _observe(diagnostic, method, *args, **kwargs):
    """Keep even observer failures outside the enrichment decision boundary."""
    try:
        getattr(diagnostic, method)(*args, **kwargs)
    except Exception:
        pass


def _code(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return (value[2:] if value.startswith('KV') else value) or None


def _index(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and re.fullmatch(r'[0-9]+', value.strip()):
        number = int(value)
        return number if number > 0 else None
    return None


def _missing_date(episode):
    # Invalid nonempty legacy dates are NOT silently repaired or removed.
    try:
        return normalize_date(episode.get('originally_available_at')) is None
    except ValueError:
        return False


def _broadcast_date(value):
    # The raw API uses compact calendar dates. Never take dates from images or broad_dt.
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if isinstance(value, str) and re.fullmatch(r'[0-9]{8}', value):
        value = f'{value[:4]}-{value[4:6]}-{value[6:]}'
    try:
        return normalize_date(value)
    except ValueError:
        return None


def _fetch_rows(client, program_id, diagnostic=None):
    _observe(diagnostic, 'record', stage='PROGRAM_API')
    program = client.get_program_programid(program_id)
    _observe(diagnostic, 'record', stage='PROGRAM_RESPONSE')
    _observe(diagnostic, 'record', program_match=(
        _code(program.get('code')) == program_id if isinstance(program, dict) else None))
    if not isinstance(program, dict) or _code(program.get('code')) != program_id:
        _observe(diagnostic, 'record', reason='NO_PROGRAM_MATCH' if isinstance(program, dict) else 'PROGRAM_RESPONSE_INVALID')
        return None
    rows = []
    seen_pages = set()
    for page in range(1, MAX_PAGES + 1):
        _observe(diagnostic, 'record', stage='PAGE_API', page=page)
        _observe(diagnostic, 'start_page', page)
        payload = client.get_frequency_programid(program_id, page=page)
        _observe(diagnostic, 'record', stage='PAGE_RESPONSE')
        _observe(diagnostic, 'page', payload)
        if not isinstance(payload, dict) or payload.get('has_more') not in ('Y', 'N'):
            _observe(diagnostic, 'record', reason='PAGE_RESPONSE_INVALID')
            return None
        items = payload.get('result')
        if not isinstance(items, list):
            _observe(diagnostic, 'record', reason='PAGE_RESULT_INVALID')
            return None
        current = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('episode'), dict):
                _observe(diagnostic, 'record', reason='PAGE_EPISODE_INVALID')
                return None
            episode = item['episode']
            current.append((_code(episode.get('code')), _index(episode.get('frequency')),
                            _broadcast_date(episode.get('broadcast_date'))))
            _observe(diagnostic, 'source_date', episode.get('broadcast_date'), current[-1][2])
        if not current:
            _observe(diagnostic, 'record', reason='FETCH_COMPLETE' if payload['has_more'] == 'N' else 'EMPTY_PAGE_DISCARD')
            return rows if payload['has_more'] == 'N' else None
        signature = frozenset(current)
        if signature in seen_pages:
            _observe(diagnostic, 'record', reason='REPEATED_PAGE_DISCARD')
            return None
        seen_pages.add(signature)
        rows.extend(current)
        if payload['has_more'] == 'N':
            _observe(diagnostic, 'record', reason='FETCH_COMPLETE')
            return rows
    # Incomplete pagination can hide conflicting identities. Apply nothing, not a partial merge.
    _observe(diagnostic, 'record', reason='PAGE_CAP_REACHED_DISCARD')
    return None


def enrich_tving_dates(program_id, show_data):
    """Fill only absent dates, preserving titles, existing values and source ownership.

    Code matches are authoritative (a supplied but unmatched code never falls back).
    The API has no verified season field. Frequency fallback is limited to a show
    explicitly bound to this program, containing ONLY local season 1. This is the
    adapter's single-program/single-season convention, not inferred remote season
    metadata. Multi-season, specials and other local season numbers require codes.
    """
    try:
        diagnostic = _Diagnostics()
    except Exception:
        diagnostic = None
    # This exception boundary covers only optional enrichment. Never log exceptions,
    # API payloads or credential-bearing URLs; support_site owns its own authentication.
    try:
        if not isinstance(show_data, dict):
            _observe(diagnostic, 'record', reason='INVALID_LOCAL_SHAPE')
            return show_data
        program_id = _code(program_id)
        _observe(diagnostic, 'local', show_data, program_id)
        if not program_id:
            _observe(diagnostic, 'record', reason='INVALID_PROGRAM_ID')
            return show_data
        show_code = show_data.get('code')
        if show_code not in (None, '') and _code(show_code) != program_id:
            _observe(diagnostic, 'record', reason='LOCAL_PROGRAM_MISMATCH')
            return show_data
        seasons = show_data.get('seasons')
        if not isinstance(seasons, list):
            _observe(diagnostic, 'record', reason='INVALID_LOCAL_SHAPE')
            return show_data
        targets = []
        for season in seasons:
            if not isinstance(season, dict) or not isinstance(season.get('episodes'), list):
                _observe(diagnostic, 'record', reason='INVALID_LOCAL_SHAPE')
                return show_data
            for episode in season['episodes']:
                if not isinstance(episode, dict):
                    _observe(diagnostic, 'record', reason='INVALID_LOCAL_SHAPE')
                    return show_data
                targets.append((season, episode))
        if not any(_missing_date(episode) for _, episode in targets):
            _observe(diagnostic, 'record', reason='NO_MISSING_DATES')
            return show_data
        _observe(diagnostic, 'record', stage='SUPPORT_IMPORT')
        client = importlib.import_module('support_site').SupportTving
        rows = _fetch_rows(client, program_id, diagnostic)
        if not rows:
            if rows == []:
                _observe(diagnostic, 'record', reason='NO_SOURCE_ROWS')
            return show_data
        _observe(diagnostic, 'record', stage='MATCH', matching_started=True)
        by_code, by_frequency = defaultdict(list), defaultdict(list)
        for row_index, (code, frequency, _) in enumerate(rows):
            if code:
                by_code[code].append(row_index)
            if frequency:
                by_frequency[(1, frequency)].append(row_index)
        frequency_scope = (_code(show_code) == program_id and len(seasons) == 1
                           and _index(seasons[0].get('index')) == 1)
        target_keys = Counter((_index(season.get('index')), _index(episode.get('index')))
                              for season, episode in targets)
        matches = []
        for season, episode in targets:
            supplied_code = episode.get('code')
            if supplied_code not in (None, ''):
                _observe(diagnostic, 'count', 'code_attempts')
                candidates = by_code.get(_code(supplied_code), [])
                if len(candidates) != 1:
                    _observe(diagnostic, 'reason', 'CODE_MISMATCH' if not candidates else 'AMBIGUOUS_CODE')
            elif frequency_scope:
                _observe(diagnostic, 'count', 'frequency_attempts')
                key = (_index(season.get('index')), _index(episode.get('index')))
                candidates = by_frequency.get(key, []) if target_keys[key] == 1 else []
                if target_keys[key] != 1:
                    _observe(diagnostic, 'reason', 'DUPLICATE_TARGET')
                elif len(candidates) != 1:
                    _observe(diagnostic, 'reason', 'NO_CANDIDATE' if not candidates else 'AMBIGUOUS_FREQUENCY')
                if len(candidates) == 1:
                    source_code = rows[candidates[0]][0]
                    if source_code and len(by_code[source_code]) != 1:
                        _observe(diagnostic, 'reason', 'AMBIGUOUS_SOURCE_CODE')
                        candidates = []
            else:
                _observe(diagnostic, 'reason', 'MULTI_SEASON_SKIPPED' if len(seasons) > 1 else 'NO_SEASON1_SCOPE')
                candidates = []
            matches.append(candidates[0] if len(candidates) == 1 else None)
            if len(candidates) == 1:
                _observe(diagnostic, 'count', 'unique_candidates')
        # Include already dated targets in ownership checks, not just empty targets.
        claims = Counter(index for index in matches if index is not None)
        for index in matches:
            if index is not None and claims[index] != 1:
                _observe(diagnostic, 'reason', 'SOURCE_REUSED')
            if index is not None and not rows[index][2]:
                _observe(diagnostic, 'reason', 'MATCHED_DATE_UNAVAILABLE')
        updates = [(target, rows[index][2]) for target, index in enumerate(matches)
                   if index is not None and claims[index] == 1 and rows[index][2]
                   and _missing_date(targets[target][1])]
        if not updates:
            _observe(diagnostic, 'record', reason='NO_UPDATES')
            return show_data
        _observe(diagnostic, 'record', stage='COPY_APPLY')
        result = copy.deepcopy(show_data)
        copies = [episode for season in result['seasons'] for episode in season['episodes']]
        for target, day in updates:
            copies[target]['originally_available_at'] = day
        _observe(diagnostic, 'record', reason='APPLIED', applied=len(updates))
        return result
    except Exception:
        _observe(diagnostic, 'failure')
        return show_data
    finally:
        _observe(diagnostic, 'emit')
