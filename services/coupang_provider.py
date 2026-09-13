"""Anonymous Coupang metadata adapter; no playback, accounts or legacy fallback."""

import re
from urllib.parse import urlsplit

from ..setup import P
from .export_normalizer import normalize_date, normalize_posters, normalize_thumb


UUID_PATTERN = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
COUPANG_URL_PATTERN = (
    r'(?i)^https?://(?:www\.)?coupangplay\.com/'
    r'(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:content|titles)/'
    r'(?P<code>' + UUID_PATTERN + r')/?(?:[?#].*)?$'
)
API_BASE = 'https://discover.coupangstreaming.com/v1/discover/titles/'
MAX_SEASONS = 30
REQUEST_TIMEOUT = (5, 15)


class _Failure(Exception):
    """Contains only a locally defined, non-sensitive reason code."""


def extract_coupang_title_code(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if value.startswith('KC'):
        value = value[2:]
    if re.fullmatch(UUID_PATTERN, value, re.IGNORECASE):
        return value.lower()
    match = re.fullmatch(COUPANG_URL_PATTERN, value)
    return match.group('code').lower() if match else ''


def _report(reason):
    try:
        P.logger.info('COUPANG_PUBLIC reason=%s', reason)
    except Exception:
        pass


def _request(http_get, code, season=None, terminal=False):
    url = API_BASE + code
    if season is not None:
        url += '/episodes?season=' + str(season)
    try:
        response = http_get(
            url, headers={'User-Agent': 'make_yaml', 'Accept': 'application/json'},
            timeout=REQUEST_TIMEOUT, allow_redirects=False,
        )
    except Exception:
        raise _Failure('REQUEST_FAILED') from None
    try:
        status = response.status_code
        # Do not follow redirects or retry authentication/throttling failures.
        if status not in (200, 400):
            raise _Failure('HTTP_FAILED')
        try:
            payload = response.json()
        except Exception:
            raise _Failure('INVALID_JSON') from None
        if not isinstance(payload, dict):
            raise _Failure('INVALID_RESPONSE')
        if status == 400:
            error = payload.get('error')
            if (terminal and isinstance(error, dict)
                    and error.get('name') == 'SeasonNotFound'
                    and error.get('code') == 'DI-7011'):
                return []
            raise _Failure('API_REJECTED')
        if 'error' in payload or 'data' not in payload:
            raise _Failure('INVALID_RESPONSE')
        return payload['data']
    finally:
        response.close()


def _number(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise _Failure('INVALID_NUMBER')
    return value


def _text(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise _Failure('INVALID_TEXT')
    return value


def _image(item, key):
    images = item.get('images')
    if images is None:
        return None
    if not isinstance(images, dict):
        raise _Failure('INVALID_IMAGE')
    image = images.get(key)
    if image is None:
        return None
    if not isinstance(image, dict):
        raise _Failure('INVALID_IMAGE')
    url = normalize_thumb(image.get('url'))
    if url and (urlsplit(url).scheme not in ('https', 'http') or not urlsplit(url).netloc):
        raise _Failure('INVALID_IMAGE')
    return url


def _episode(item, index):
    episode = {'index': index, 'title': _text(item.get('title')),
               'summary': _text(item.get('description'))}
    thumb = _image(item, 'story-art')
    if thumb:
        episode['thumbs'] = thumb
    # This is the provider's publication calendar day, not an inferred original
    # broadcast date. Shared normalization deliberately does not shift timezone.
    day = normalize_date(item.get('published_at'))
    if day:
        episode['originally_available_at'] = day
    return episode


def build_coupang_show_data(code, http_get=None):
    """Build a fresh show or return None, never a partially collected show.

    http_get is injectable for offline fixtures. Runtime requests are anonymous,
    bounded, without retries; the opaque COUPANG class is never invoked here.
    """
    try:
        code = extract_coupang_title_code(code)
        if not code:
            raise _Failure('INVALID_ID')
        if http_get is None:
            import requests
            http_get = requests.get
        detail = _request(http_get, code)
        if not isinstance(detail, dict) or detail.get('id') != code:
            raise _Failure('TITLE_MISMATCH')
        title = _text(detail.get('title'))
        if not title.strip():
            raise _Failure('MISSING_TITLE')
        show = {'primary': False, 'code': 'KC' + code, 'title': title,
                'summary': _text(detail.get('description')), 'seasons': []}
        poster = _image(detail, 'poster') or _image(detail, 'story-art')
        if poster:
            show['posters'] = normalize_posters(poster)
        if detail.get('as') == 'MOVIE':
            # Explicit compatibility representation, not real movie episode IDs.
            show['seasons'] = [{'index': 1, 'episodes': [_episode(detail, 1)]}]
        elif detail.get('as') == 'TVSHOW':
            count = _number(detail.get('seasons'), 1)
            if count > MAX_SEASONS:
                raise _Failure('SEASON_CAP_REACHED')
            declared = detail.get('seasonList')
            if declared is not None:
                if (not isinstance(declared, list)
                        or any(type(n) is not int for n in declared)
                        or sorted(declared) != list(range(1, count + 1))):
                    raise _Failure('SEASON_LIST_MISMATCH')
            seen_ids = set()
            for season in range(1, count + 1):
                rows = _request(http_get, code, season)
                if not isinstance(rows, list) or not rows:
                    raise _Failure('EMPTY_OR_INVALID_SEASON')
                episodes = []
                seen_numbers = set()
                for item in rows:
                    if not isinstance(item, dict) or _number(item.get('season'), 1) != season:
                        raise _Failure('EPISODE_SEASON_MISMATCH')
                    if item.get('parent_id', code) != code:
                        raise _Failure('EPISODE_PARENT_MISMATCH')
                    episode_id = item.get('id')
                    if not isinstance(episode_id, str) or not re.fullmatch(UUID_PATTERN, episode_id, re.IGNORECASE):
                        raise _Failure('INVALID_EPISODE_ID')
                    episode_id = episode_id.lower()
                    index = _number(item.get('episode'))
                    if index in seen_numbers or episode_id in seen_ids:
                        raise _Failure('DUPLICATE_EPISODE')
                    seen_numbers.add(index)
                    seen_ids.add(episode_id)
                    episodes.append(_episode(item, index))
                # The API may return newest first. Preserve numbers, sort only.
                show['seasons'].append({'index': season, 'episodes': sorted(
                    episodes, key=lambda item: item['index'])})
            # Cross-check the count. Only an explicit SeasonNotFound (or a 200
            # empty array) is a terminal marker; arbitrary 400 is never success.
            extra = _request(http_get, code, count + 1, terminal=True)
            if extra != []:
                raise _Failure('SEASON_COUNT_MISMATCH')
        else:
            raise _Failure('UNSUPPORTED_TYPE')
        _report('OK')
        return show
    except _Failure as error:
        _report(str(error))
    except Exception:
        # No exception text, payloads, credentials or URLs in diagnostics.
        _report('INVALID_METADATA_OR_CLIENT')
    return None
