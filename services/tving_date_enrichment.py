"""Optional, non-mutating Tving date enrichment; authentication stays in support_site."""

import copy
import importlib
import re
from collections import Counter, defaultdict

from .export_normalizer import normalize_date


MAX_PAGES = 10


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


def _fetch_rows(client, program_id):
    program = client.get_program_programid(program_id)
    if not isinstance(program, dict) or _code(program.get('code')) != program_id:
        return None
    rows = []
    seen_pages = set()
    for page in range(1, MAX_PAGES + 1):
        payload = client.get_frequency_programid(program_id, page=page)
        if not isinstance(payload, dict) or payload.get('has_more') not in ('Y', 'N'):
            return None
        items = payload.get('result')
        if not isinstance(items, list):
            return None
        current = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('episode'), dict):
                return None
            episode = item['episode']
            current.append((_code(episode.get('code')), _index(episode.get('frequency')),
                            _broadcast_date(episode.get('broadcast_date'))))
        if not current:
            return rows if payload['has_more'] == 'N' else None
        signature = frozenset(current)
        if signature in seen_pages:
            return None
        seen_pages.add(signature)
        rows.extend(current)
        if payload['has_more'] == 'N':
            return rows
    # Incomplete pagination can hide conflicting identities. Apply nothing, not a partial merge.
    return None


def enrich_tving_dates(program_id, show_data):
    """Fill only absent dates, preserving titles, existing values and source ownership.

    Code matches are authoritative (a supplied but unmatched code never falls back).
    The API has no verified season field. Frequency fallback is limited to a show
    explicitly bound to this program, containing ONLY local season 1. This is the
    adapter's single-program/single-season convention, not inferred remote season
    metadata. Multi-season, specials and other local season numbers require codes.
    """
    if not isinstance(show_data, dict):
        return show_data
    # This exception boundary covers only optional enrichment. Never log exceptions,
    # API payloads or credential-bearing URLs; support_site owns its own authentication.
    try:
        program_id = _code(program_id)
        if not program_id:
            return show_data
        show_code = show_data.get('code')
        if show_code not in (None, '') and _code(show_code) != program_id:
            return show_data
        seasons = show_data.get('seasons')
        if not isinstance(seasons, list):
            return show_data
        targets = []
        for season in seasons:
            if not isinstance(season, dict) or not isinstance(season.get('episodes'), list):
                return show_data
            for episode in season['episodes']:
                if not isinstance(episode, dict):
                    return show_data
                targets.append((season, episode))
        if not any(_missing_date(episode) for _, episode in targets):
            return show_data
        client = importlib.import_module('support_site').SupportTving
        rows = _fetch_rows(client, program_id)
        if not rows:
            return show_data
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
                candidates = by_code.get(_code(supplied_code), [])
            elif frequency_scope:
                key = (_index(season.get('index')), _index(episode.get('index')))
                candidates = by_frequency.get(key, []) if target_keys[key] == 1 else []
                if len(candidates) == 1:
                    source_code = rows[candidates[0]][0]
                    if source_code and len(by_code[source_code]) != 1:
                        candidates = []
            else:
                candidates = []
            matches.append(candidates[0] if len(candidates) == 1 else None)
        # Include already dated targets in ownership checks, not just empty targets.
        claims = Counter(index for index in matches if index is not None)
        updates = [(target, rows[index][2]) for target, index in enumerate(matches)
                   if index is not None and claims[index] == 1 and rows[index][2]
                   and _missing_date(targets[target][1])]
        if not updates:
            return show_data
        result = copy.deepcopy(show_data)
        copies = [episode for season in result['seasons'] for episode in season['episodes']]
        for target, day in updates:
            copies[target]['originally_available_at'] = day
        return result
    except Exception:
        return show_data
