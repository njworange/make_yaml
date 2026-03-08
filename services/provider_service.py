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
    'drm': 'wm',
    'client_version': '7.1.40',
}
WAVVE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Origin': 'https://www.wavve.com',
    'Referer': 'https://www.wavve.com/',
}


def log_wavve_http_error(response, context):
    body = ''
    try:
        body = response.text[:300]
    except Exception:
        pass
    logger.error(
        f"Wavve {context} http_error status={response.status_code} "
        f"url={response.url} body={body}"
    )


def create_wavve_session(program_id=None):
    session = requests.Session()
    session.headers.update(WAVVE_HEADERS)
    referer = 'https://www.wavve.com/'
    if program_id:
        referer = f'https://www.wavve.com/player/vod?programid={program_id}'
    session.headers['Referer'] = referer
    return session


def bootstrap_wavve_session(session, program_id):
    params = dict(WAVVE_API_PARAMS)
    try:
        session.get(f'https://www.wavve.com/player/vod?programid={program_id}', timeout=10)
        ip_response = session.get('https://apis.wavve.com/ip', params=params, timeout=10)
        if ip_response.ok:
            logger.debug(f"Wavve ip bootstrap program_id={program_id} ok")
        guid_response = session.get('https://apis.wavve.com/guid/issue', params=params, timeout=10)
        if guid_response.ok:
            guid = (guid_response.json().get('guid') or '').strip()
            if guid:
                params['guid'] = guid
                logger.debug(f"Wavve guid bootstrap program_id={program_id} guid={guid}")
        knock_response = session.get('https://apis.wavve.com/knock', params=params, timeout=10)
        if knock_response.ok:
            logger.debug(f"Wavve knock bootstrap program_id={program_id} ok")
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    return params


def parse_wavve_release_date(cell):
    release_date = (cell.get('releasedate') or '').strip()
    if release_date:
        return release_date
    for title_info in cell.get('title_list', []):
        text = (title_info.get('text') or '').strip()
        match = re.search(r'(20\d{2}-\d{2}-\d{2})', text)
        if match:
            return match.group(1)
    return ''


def parse_wavve_episode_number(value):
    text = str(value or '').strip()
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else ''


def build_wavve_episode_metadata(cell):
    normalized_title = normalize_tving_episode_title(cell.get('episodetitle', ''))
    return {
        'releasedate': parse_wavve_release_date(cell),
        'title': normalized_title,
        'episodenumber': parse_wavve_episode_number(cell.get('episodenumber')),
    }


def fetch_wavve_episode_metadata_from_support_site(program_id):
    metadata_by_title = {}
    metadata_by_index = {}
    try:
        from support_site import SupportWavve
        page = 1
        while True:
            episode_data = SupportWavve.vod_program_contents_programid(program_id, page=page)
            episode_list = episode_data.get('list') or []
            if not episode_list:
                break
            for episode in episode_list:
                episode_metadata = build_wavve_episode_metadata(episode)
                metadata_by_title[episode_metadata['title']] = episode_metadata
                episode_number = episode_metadata['episodenumber']
                if episode_number:
                    metadata_by_index[episode_number] = episode_metadata
            if episode_data.get('pagecount') == episode_data.get('count') or page == 10:
                break
            page += 1
        logger.debug(
            f"Wavve support_site metadata fetched program_id={program_id} "
            f"title_entries={len(metadata_by_title)} index_entries={len(metadata_by_index)}"
        )
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    return {
        'by_title': metadata_by_title,
        'by_index': metadata_by_index,
    }


def extract_wavve_orderby(program_id):
    session = create_wavve_session(program_id)
    params = bootstrap_wavve_session(session, program_id)
    try:
        response = session.get(
            'https://apis.wavve.com/fz/vod/programs/landing',
            params={**params, 'history': 'all', 'programid': program_id},
            timeout=10,
        )
        if not response.ok:
            log_wavve_http_error(response, 'landing')
        response.raise_for_status()
        payload = response.json()
        for tab in payload.get('landing_list', {}).get('tab', []):
            if tab.get('type') == 'episode':
                path = tab.get('path', '')
                match = re.search(r'orderby=([a-z]+)', path)
                if match:
                    return match.group(1)
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    return ''


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
    support_site_metadata = fetch_wavve_episode_metadata_from_support_site(program_id)
    if support_site_metadata.get('by_index') or support_site_metadata.get('by_title'):
        return support_site_metadata
    session = create_wavve_session(program_id)
    base_params = bootstrap_wavve_session(session, program_id)
    metadata_by_title = {}
    metadata_by_index = {}
    limit = min(max(episode_count, 1), 100)
    orderby_candidates = []
    preferred_orderby = extract_wavve_orderby(program_id)
    for value in [preferred_orderby, 'new', 'old']:
        if value and value not in orderby_candidates:
            orderby_candidates.append(value)
    for orderby in orderby_candidates:
        offset = 0
        while len(metadata_by_index) < episode_count:
            try:
                response = session.get(
                    f'https://apis.wavve.com/fz/vod/programs/{program_id}/contents',
                    params={**base_params, 'limit': limit, 'offset': offset, 'orderby': orderby},
                    timeout=10,
                )
                if not response.ok:
                    log_wavve_http_error(response, f'contents orderby={orderby} offset={offset}')
                response.raise_for_status()
                payload = response.json()
                cell_list = payload.get('cell_toplist', {}).get('celllist', [])
                if not cell_list:
                    break
                for cell in cell_list:
                    episode_metadata = build_wavve_episode_metadata(cell)
                    normalized_title = episode_metadata['title']
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
    if isinstance(show_data.get('summary'), str) and show_data['summary'].startswith('"'):
        show_data['summary'] = show_data['summary'][1:].strip()
    episode_count = sum(len(season.get('episodes', [])) for season in show_data.get('seasons', []))
    episode_metadata = fetch_wavve_episode_metadata(program_id, episode_count)
    for season in show_data.get('seasons', []):
        if isinstance(season.get('summary'), str) and season['summary'].startswith('"'):
            season['summary'] = season['summary'][1:].strip()
        for episode in season.get('episodes', []):
            original_title = normalize_tving_episode_title(episode.get('title', ''))
            metadata = episode_metadata.get('by_index', {}).get(str(episode.get('index', '')), {})
            if not metadata:
                metadata = episode_metadata.get('by_title', {}).get(original_title, {})
            air_date = (episode.get('originally_available_at') or metadata.get('releasedate') or '').strip()
            if air_date:
                episode['originally_available_at'] = air_date
                logger.debug(f"Wavve episode normalized index={episode.get('index')} air_date={air_date} title={original_title}")
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
