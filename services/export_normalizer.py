"""Non-destructive formatting at the YAML export boundary (no provider I/O)."""

import copy
from datetime import date, datetime

from .episode_title import format_episode_title


TOP_LEVEL_KEY_ORDER = ['primary', 'code', 'title', 'posters', 'seasons']
SEASON_KEY_ORDER = ['index', 'posters', 'title', 'episodes']
EPISODE_KEY_ORDER = ['index', 'title', 'summary', 'thumbs', 'originally_available_at']


def reorder_keys(value, key_order):
    """Keep extension fields, in their existing order, after the core fields."""
    result = {key: value[key] for key in key_order if key in value}
    result.update((key, item) for key, item in value.items() if key not in key_order)
    return result


def normalize_posters(value):
    if value is None or value == '' or value == {}:
        return []
    items = value if isinstance(value, list) else [value]
    posters = []
    for item in items:
        if item is None or item == '' or item == {}:
            continue
        if isinstance(item, str):
            if item.strip():
                posters.append({'url': item.strip()})
        elif isinstance(item, dict) and 'url' in item:
            if item['url'] is None:
                continue
            if not isinstance(item['url'], str):
                raise ValueError('poster url must be a string')
            if item['url'].strip():
                poster = copy.deepcopy(item)
                poster['url'] = item['url'].strip()
                posters.append(poster)
        else:
            raise ValueError('posters must contain URL strings or mappings with a string url')
    return posters


def normalize_thumb(value):
    """Select the first supplied URL, never substitute show/season artwork.

    `url` is the export image key; `value` is the adjacent TMDB art key.
    Unknown nonempty shapes are rejected rather than stringified or discarded.
    """
    if value is None or value == '' or value == [] or value == {}:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for item in value:
            url = normalize_thumb(item)
            if url:
                return url
        return None
    if isinstance(value, dict):
        for key in ('url', 'value'):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        if any(key in value for key in ('url', 'value')) and all(
            value.get(key) is None or value.get(key) == ''
            for key in ('url', 'value')
        ):
            return None
    raise ValueError('thumbs must contain a URL string or a supported url/value mapping')


def normalize_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Do not infer dates from URLs, arbitrary text, epoch numbers or other episodes.
        for date_format in ('%Y-%m-%d', '%Y.%m.%d'):
            try:
                parsed = datetime.strptime(value, date_format).date()
                canonical = parsed.isoformat()
                if (canonical if date_format == '%Y-%m-%d' else canonical.replace('-', '.')) == value:
                    return parsed.isoformat()
            except ValueError:
                pass
        # A supplied ISO datetime retains its own calendar day (no timezone shift).
        if len(value) > 10 and value[10] in ('T', ' '):
            try:
                day = datetime.strptime(value[:10], '%Y-%m-%d').date()
                if day.isoformat() == value[:10]:
                    return datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
            except ValueError:
                pass
    raise ValueError('originally_available_at must be a valid YYYY-MM-DD date')


def normalize_optional_fields(value):
    if 'posters' in value:
        value['posters'] = normalize_posters(value['posters'])
    if 'thumbs' in value:
        thumb = normalize_thumb(value['thumbs'])
        if thumb is None:
            value.pop('thumbs')
        else:
            value['thumbs'] = thumb
    if 'originally_available_at' in value:
        date_text = normalize_date(value['originally_available_at'])
        if date_text is None:
            value.pop('originally_available_at')
        else:
            value['originally_available_at'] = date_text


def normalize_export_data(show_data):
    """Normalize only show/season/episode fields, not arbitrary extension objects.

    Missing metadata stays missing. This is not an episode completeness validator
    and does not change primary semantics, season/episode numbering or
    provider availability. Existing title-deletion policy is applied by the writer.
    """
    if not isinstance(show_data, dict):
        raise ValueError('YAML export requires a show mapping')
    result = copy.deepcopy(show_data)
    normalize_optional_fields(result)
    seasons = result.get('seasons', [])
    if not isinstance(seasons, list):
        raise ValueError('seasons must be a list')
    for index, season in enumerate(seasons):
        if not isinstance(season, dict):
            raise ValueError('each season must be a mapping')
        normalize_optional_fields(season)
        episodes = season.get('episodes', [])
        if not isinstance(episodes, list):
            raise ValueError('episodes must be a list')
        for episode_index, episode in enumerate(episodes):
            if not isinstance(episode, dict):
                raise ValueError('each episode must be a mapping')
            normalize_optional_fields(episode)
            # Display decoration belongs here, after TMDB and date normalization,
            # never in provider parsing or in the Korean metadata acceptance gate.
            if 'title' in episode or episode.get('originally_available_at'):
                episode['title'] = format_episode_title(
                    episode.get('title'), episode.get('originally_available_at')
                )
            episode.pop('code', None)
            episodes[episode_index] = reorder_keys(episode, EPISODE_KEY_ORDER)
        seasons[index] = reorder_keys(season, SEASON_KEY_ORDER)
    return reorder_keys(result, TOP_LEVEL_KEY_ORDER)
