import copy
import re
import traceback
from datetime import datetime

import requests

from ..providers.legacy_registry import get_provider_class
from ..setup import P

logger = P.logger

KOREAN_WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
WAVVE_API_PARAMS = {
    'apikey': 'E5F3E0D30947AA5440556471321BB6D9',
    'device': 'pc',
    'partner': 'pooq',
    'region': 'kor',
    'targetage': 'all',
    'pooqzone': 'none',
    'guid': 'none',
    'drm': 'wm',
    'client_version': '7.1.40',
}


def extract_date_from_tving_thumb(url):
    if not url:
        return ''
    match = re.search(r'/(20\d{2})(\d{2})(\d{2})/', url)
    if not match:
        return ''
    return f'{match.group(1)}-{match.group(2)}-{match.group(3)}'


def format_korean_broadcast_date(date_text):
    if not date_text:
        return ''
    date_text = date_text[:10]
    try:
        parsed = datetime.strptime(date_text, '%Y-%m-%d')
        return f"{parsed:%Y.%m.%d}({KOREAN_WEEKDAYS[parsed.weekday()]})"
    except ValueError:
        return ''


def normalize_tving_episode_title(title):
    title = (title or '').strip()
    return re.sub(r'^\d+\.\s*', '', title)


def fetch_wavve_episode_metadata(program_id, episode_count):
    metadata_by_title = {}
    metadata_by_index = {}
    offset = 0
    limit = min(max(episode_count, 1), 100)
    while len(metadata_by_index) < episode_count:
        try:
            response = requests.get(
                f'https://apis.wavve.com/fz/vod/programs/{program_id}/contents',
                params={**WAVVE_API_PARAMS, 'limit': limit, 'offset': offset, 'orderby': 'new'},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            cell_list = payload.get('cell_toplist', {}).get('celllist', [])
            if not cell_list:
                break
            for cell in cell_list:
                normalized_title = normalize_tving_episode_title(cell.get('episodetitle', ''))
                episode_metadata = {
                    'releasedate': (cell.get('releasedate') or '').strip(),
                    'title': normalized_title,
                    'episodenumber': str(cell.get('episodenumber') or '').strip(),
                }
                metadata_by_title[normalized_title] = episode_metadata
                episode_number = episode_metadata['episodenumber']
                if episode_number:
                    metadata_by_index[episode_number] = episode_metadata
            offset += len(cell_list)
            if len(cell_list) < limit:
                break
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
            break
    logger.debug(
        f"Wavve metadata fetched program_id={program_id} "
        f"title_entries={len(metadata_by_title)} index_entries={len(metadata_by_index)}"
    )
    return {
        'by_title': metadata_by_title,
        'by_index': metadata_by_index,
    }


def normalize_wavve_show_data(program_id, show_data):
    if not isinstance(show_data, dict):
        return show_data
    episode_count = sum(len(season.get('episodes', [])) for season in show_data.get('seasons', []))
    episode_metadata = fetch_wavve_episode_metadata(program_id, episode_count)
    for season in show_data.get('seasons', []):
        for episode in season.get('episodes', []):
            original_title = normalize_tving_episode_title(episode.get('title', ''))
            metadata = episode_metadata.get('by_index', {}).get(str(episode.get('index', '')), {})
            if not metadata:
                metadata = episode_metadata.get('by_title', {}).get(original_title, {})
            air_date = (episode.get('originally_available_at') or metadata.get('releasedate') or '').strip()
            if air_date:
                episode['originally_available_at'] = air_date
            date_prefix = format_korean_broadcast_date(air_date)
            if date_prefix and original_title:
                episode['title'] = f'{date_prefix} {original_title}'
            elif original_title:
                episode['title'] = original_title
    return show_data


def normalize_tving_show_data(show_data):
    if not isinstance(show_data, dict):
        return show_data
    for season in show_data.get('seasons', []):
        for episode in season.get('episodes', []):
            original_title = normalize_tving_episode_title(episode.get('title', ''))
            air_date = (episode.get('originally_available_at') or '').strip()
            if not air_date:
                air_date = extract_date_from_tving_thumb(episode.get('thumbs', ''))
                if air_date:
                    episode['originally_available_at'] = air_date
            date_prefix = format_korean_broadcast_date(air_date)
            if date_prefix and original_title:
                episode['title'] = f'{date_prefix} {original_title}'
            elif original_title:
                episode['title'] = original_title
    return show_data


def get_show_data(code):
    try:
        logger.debug(code)
        site = code[:2]
        site_code = code[2:]
        logger.debug(f"YAMLUTILS get_data parsed site={site} code={site_code}")
        provider_class = get_provider_class(site)
        show_data = provider_class.make_data(site_code)
        if site == 'KV':
            show_data = normalize_tving_show_data(show_data)
        elif site == 'KW':
            show_data = normalize_wavve_show_data(site_code, show_data)
        if isinstance(show_data, dict):
            logger.debug(f"YAMLUTILS get_data result site={site} type=dict keys={list(show_data.keys())} seasons={len(show_data.get('seasons', []))}")
        elif isinstance(show_data, list):
            logger.debug(f"YAMLUTILS get_data result site={site} type=list len={len(show_data)}")
        else:
            logger.debug(f"YAMLUTILS get_data result site={site} type={type(show_data).__name__} truthy={bool(show_data)}")
        if P.ModelSetting.get_int('split_season') != 1:
            season_data = []
            split_season = P.ModelSetting.get_int('split_season')
            for season in show_data['seasons']:
                index = int(season['index'])
                for split_index in range(split_season):
                    season_data.append({
                        'index': int(split_index * 100 + index),
                        'summary': copy.deepcopy(season.get('summary', '')),
                        'episodes': copy.deepcopy(season['episodes']),
                    })
            show_data['seasons'] = season_data
        return show_data
    except Exception as e:
        logger.error(f"Exception:{e} [site={site if 'site' in locals() else ''} code={site_code if 'site_code' in locals() else ''}]")
        logger.error(traceback.format_exc())
