import copy
import html
import importlib
import json
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
EBS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}
APPLE_TV_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


def extract_ebs_program_id(value):
    text = str(value or '').strip()
    match = re.search(r'anikids\.ebs\.co\.kr/anikids/program/show/(?P<code>[A-Za-z0-9]+)', text)
    if match:
        return match.group('code')
    return text


def extract_appletv_show_id(value):
    text = str(value or '').strip()
    match = re.search(r'(umc\.cmc\.[A-Za-z0-9]+)', text)
    if match:
        return match.group(1)
    return text


def decode_ebs_text(value):
    text = html.unescape(str(value or ''))
    text = text.replace('&nbsp;', ' ')
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text.replace('\xa0', ' '))
    return text.strip()


def fetch_ebs_html(url):
    response = requests.get(url, headers=EBS_HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def fetch_appletv_html(url):
    response = requests.get(url, headers=APPLE_TV_HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def extract_ebs_meta_content(page_html, property_name):
    match = re.search(
        rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\'](?P<value>.*?)["\']',
        page_html,
        flags=re.I | re.S,
    )
    if match:
        return decode_ebs_text(match.group('value'))
    return ''


def extract_ebs_json_object(page_html, variable_name):
    match = re.search(
        rf'var\s+{re.escape(variable_name)}\s*=\s*(\{{.*?\n\t\}}|\{{.*?\n\}}|\{{.*?\}});',
        page_html,
        flags=re.S,
    )
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except Exception:
        return {}


def extract_ebs_season_entries(page_html):
    entries = []
    seen_step_ids = set()
    pattern = re.compile(
        r"changeSteps01\('(?P<step_id>[^']+)'\).*?>(?P<label>[^<]+)</a>",
        flags=re.S,
    )
    for match in pattern.finditer(page_html):
        step_id = match.group('step_id').strip()
        label = decode_ebs_text(match.group('label'))
        if not step_id or step_id in seen_step_ids:
            continue
        seen_step_ids.add(step_id)
        season_number_match = re.search(r'시즌\s*(\d+)', label)
        season_index = int(season_number_match.group(1)) if season_number_match else len(entries) + 1
        entries.append({
            'step_id': step_id,
            'label': label,
            'index': season_index,
        })
    return entries


def extract_ebs_default_course_id(page_html, program_id):
    match = re.search(r'data-vod="/vodCommon/show\?siteCd=AK&courseId=(?P<course_id>[A-Za-z0-9]+)', page_html)
    if match:
        return match.group('course_id')
    return program_id


def normalize_ebs_episode_title(title):
    title = decode_ebs_text(title)
    title = re.sub(r'^\d+\.\s*', '', title)
    return title.strip()


def normalize_ebs_date(date_text):
    text = decode_ebs_text(date_text)
    match = re.search(r'(20\d{2})\.(\d{2})\.(\d{2})', text)
    if not match:
        return ''
    return f'{match.group(1)}-{match.group(2)}-{match.group(3)}'


def extract_ebs_episodes(page_html):
    episodes = []
    pattern = re.compile(
        r'<a\s+href="(?P<href>/vodCommon/show\?siteCd=AK&courseId=[^"]+&lectId=(?P<lect_id>[^&"]+)&stepId=(?P<step_id>[^"]+))".*?'
        r'<img\s+src="(?P<thumb>[^"]*)".*?'
        r'<p>(?P<title>.*?)</p>\s*<span>(?P<date>[^<]+)</span>',
        flags=re.S,
    )
    seen_lect_ids = set()
    for match in pattern.finditer(page_html):
        lect_id = match.group('lect_id').strip()
        if not lect_id or lect_id in seen_lect_ids:
            continue
        seen_lect_ids.add(lect_id)
        title = normalize_ebs_episode_title(match.group('title'))
        date_text = normalize_ebs_date(match.group('date'))
        episode_number_match = re.match(r'^(\d+)', decode_ebs_text(match.group('title')))
        index = int(episode_number_match.group(1)) if episode_number_match else len(episodes) + 1
        episodes.append({
            'index': index,
            'title': title,
            'summary': '',
            'thumbs': match.group('thumb').strip(),
            'originally_available_at': date_text,
            'code': lect_id,
        })
    return episodes


def build_ebs_show_data(program_id):
    program_id = extract_ebs_program_id(program_id)
    if not program_id:
        return None
    program_url = f'https://anikids.ebs.co.kr/anikids/program/show/{program_id}'
    program_html = fetch_ebs_html(program_url)
    course_id = extract_ebs_default_course_id(program_html, program_id)
    show_title = extract_ebs_meta_content(program_html, 'og:title')
    show_summary = extract_ebs_meta_content(program_html, 'og:description')
    seasons = []
    earliest_date = ''
    season_entries = extract_ebs_season_entries(program_html)
    if not season_entries:
        season_entries = [{'step_id': '', 'label': '', 'index': 1}]
    for season_entry in season_entries:
        season_url = (
            'https://anikids.ebs.co.kr/vodCommon/show?'
            f'siteCd=AK&courseId={course_id}'
        )
        if season_entry['step_id']:
            season_url += f'&stepId={season_entry["step_id"]}'
        season_html = fetch_ebs_html(season_url)
        vod_option = extract_ebs_json_object(season_html, 'vodOption')
        season_title = decode_ebs_text(vod_option.get('stepNm') or season_entry['label'])
        episodes = extract_ebs_episodes(season_html)
        if not episodes:
            continue
        for episode in episodes:
            air_date = episode.get('originally_available_at') or ''
            if air_date and (not earliest_date or air_date < earliest_date):
                earliest_date = air_date
        seasons.append({
            'index': season_entry['index'],
            'title': season_title,
            'summary': '',
            'episodes': episodes,
        })
    if not seasons:
        return None
    show_data = {
        'title': show_title,
        'summary': show_summary,
        'seasons': sorted(seasons, key=lambda item: item.get('index', 0)),
    }
    if earliest_date:
        show_data['originally_available_at'] = earliest_date
    return show_data


def extract_appletv_meta_content(page_html, property_name):
    match = re.search(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(property_name)}["\'][^>]+content=["\'](?P<value>.*?)["\']',
        page_html,
        flags=re.I | re.S,
    )
    if match:
        return decode_ebs_text(match.group('value'))
    return ''


def extract_appletv_json_ld(page_html, script_id):
    match = re.search(
        rf'<script[^>]+id=(?:["\'])?{re.escape(script_id)}(?:["\'])?[^>]*>(?P<value>.*?)</script>',
        page_html,
        flags=re.I | re.S,
    )
    if not match:
        return {}
    try:
        return json.loads(match.group('value').strip())
    except Exception:
        return {}


def normalize_appletv_duration(value):
    text = decode_ebs_text(value)
    text = text.replace(' ', '')
    match = re.search(r'(\d+)분', text)
    if match:
        return int(match.group(1))
    match = re.search(r'(\d+)m', text)
    if match:
        return int(match.group(1))
    return 0


def extract_appletv_genres(page_html):
    match = re.search(r'<span class="metadata-list[^"]*"[^>]*>(?P<value>.*?)</span>', page_html, flags=re.S)
    if not match:
        return []
    text = decode_ebs_text(match.group('value'))
    parts = [part.strip() for part in text.split('·')]
    return [part for part in parts if part and part != 'TV 프로그램']


def extract_appletv_personnel(page_html, title_text):
    actor_match = re.search(r'<span class="personnel-title[^"]*">출연</span>\s*<span class="personnel-list[^"]*">(?P<value>.*?)</span>', page_html, flags=re.S)
    if not actor_match:
        return []
    people = []
    for person_match in re.finditer(r'>(?P<name>[^<]+)</a>', actor_match.group('value')):
        name = decode_ebs_text(person_match.group('name'))
        if name and name != title_text:
            people.append(name)
    return people


def extract_appletv_season_blocks(page_html):
    blocks = []
    direct_pattern = re.compile(
        r'<h2 class="title[^"]*"[^>]*><span class="dir-wrapper"[^>]*>(?P<title>시즌\s*\d+)</span></h2>(?P<body>.*?)(?=<h2 class="title|</main>)',
        flags=re.S,
    )
    for match in direct_pattern.finditer(page_html):
        blocks.append((decode_ebs_text(match.group('title')), match.group('body')))
    if blocks:
        return blocks

    select_match = re.search(
        r'data-testid="accessory-button-select-text">\s*(?P<title>시즌\s*\d+)\s*</div>(?P<body>.*?)(?=</main>)',
        page_html,
        flags=re.S,
    )
    if select_match:
        return [(decode_ebs_text(select_match.group('title')), select_match.group('body'))]
    return []


def extract_appletv_current_season_title(page_html):
    match = re.search(
        r'data-testid="accessory-button-select-text">\s*(?P<title>시즌\s*\d+)\s*</div>',
        page_html,
        flags=re.S,
    )
    if match:
        return decode_ebs_text(match.group('title'))
    match = re.search(r'>(?P<title>시즌\s*\d+)<', page_html)
    if match:
        return decode_ebs_text(match.group('title'))
    return '시즌 1'


def extract_appletv_episodes(season_html):
    episodes = []
    pattern = re.compile(
        r'<div class="tag[^"]*">에피소드\s*(?P<index>\d+)</div>\s*<div class="title[^"]*">(?P<title>.*?)</div>\s*<div class="description[^"]*">(?P<summary>.*?)</div>.*?<div class="duration[^"]*"[^>]*>(?P<duration>.*?)</div>',
        flags=re.S,
    )
    for match in pattern.finditer(season_html):
        episodes.append({
            'index': int(match.group('index')),
            'title': decode_ebs_text(match.group('title')),
            'summary': decode_ebs_text(match.group('summary')),
            'runtime': normalize_appletv_duration(match.group('duration')),
            'thumbs': '',
            'originally_available_at': '',
        })
    return episodes


def build_appletv_show_data(show_id):
    show_id = extract_appletv_show_id(show_id)
    if not show_id:
        return None
    show_url = f'https://tv.apple.com/kr/show/-/{show_id}'
    page_html = fetch_appletv_html(show_url)
    series_schema = extract_appletv_json_ld(page_html, 'schema:tv-series')
    title = decode_ebs_text(series_schema.get('name') or extract_appletv_meta_content(page_html, 'apple:title'))
    title = re.sub(r'\s*보기\s*-\s*Apple\s*TV$', '', title).strip()
    summary = decode_ebs_text(series_schema.get('description') or extract_appletv_meta_content(page_html, 'description'))
    season_blocks = extract_appletv_season_blocks(page_html)
    seasons = []
    for season_title, season_body in season_blocks:
        season_number_match = re.search(r'(\d+)', season_title)
        season_index = int(season_number_match.group(1)) if season_number_match else len(seasons) + 1
        episodes = extract_appletv_episodes(season_body)
        if not episodes:
            continue
        seasons.append({
            'index': season_index,
            'title': season_title,
            'summary': '',
            'episodes': episodes,
        })
    if not seasons:
        current_season_title = extract_appletv_current_season_title(page_html)
        current_episodes = extract_appletv_episodes(page_html)
        if current_episodes:
            season_number_match = re.search(r'(\d+)', current_season_title)
            seasons.append({
                'index': int(season_number_match.group(1)) if season_number_match else 1,
                'title': current_season_title,
                'summary': '',
                'episodes': current_episodes,
            })
    logger.debug(
        f"AppleTV parse show_id={show_id} title={bool(title)} summary={bool(summary)} "
        f"schema={bool(series_schema)} season_blocks={len(season_blocks)} seasons={len(seasons)}"
    )
    if not seasons:
        if title or summary:
            return {
                'title': title or show_id,
                'summary': summary,
                'seasons': [],
            }
        return None
    show_data = {
        'title': title,
        'summary': summary,
        'seasons': seasons,
    }
    date_published = decode_ebs_text(series_schema.get('datePublished') or '')
    if len(date_published) >= 10:
        show_data['originally_available_at'] = date_published[:10]
    genres = extract_appletv_genres(page_html)
    if genres:
        show_data['extras'] = {'genres': genres}
    actors = [decode_ebs_text(actor.get('name')) for actor in series_schema.get('actor', []) if actor.get('name')]
    if not actors:
        actors = extract_appletv_personnel(page_html, title)
    if actors:
        show_data.setdefault('extras', {})['actors'] = actors
    return show_data


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
        module_name = 'support_' + 'site'
        SupportWavve = importlib.import_module(module_name).SupportWavve
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
    site = ''
    site_code = ''
    try:
        logger.debug(code)
        site = code[:2]
        site_code = code[2:]
        if site == 'KE':
            site_code = extract_ebs_program_id(site_code)
        elif site == 'FA':
            site_code = extract_appletv_show_id(site_code)
        logger.debug(f"YAMLUTILS get_data parsed site={site} code={site_code}")
        provider_class = get_provider_class(site)
        if provider_class is None and site not in ['KE', 'FA']:
            return None
        show_data = None
        if site == 'KE':
            try:
                show_data = build_ebs_show_data(site_code)
            except Exception as e:
                logger.error(f"Exception:{str(e)}")
                logger.error(traceback.format_exc())
        elif site == 'FA':
            try:
                show_data = build_appletv_show_data(site_code)
            except Exception as e:
                logger.error(f"Exception:{str(e)}")
                logger.error(traceback.format_exc())
        if show_data in (None, [], ''):
            if site == 'FA':
                logger.debug(f"AppleTV public parse empty; skipping legacy fallback site={site} code={site_code}")
            elif provider_class is not None:
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
        if P.ModelSetting.get_int('split_season') != 1 and isinstance(show_data, dict):
            show_dict = show_data
            season_data = []
            split_season = P.ModelSetting.get_int('split_season')
            for season in show_dict.get('seasons', []):
                index = int(season['index'])
                for split_index in range(split_season):
                    season_data.append({
                        'index': int(split_index * 100 + index),
                        'summary': copy.deepcopy(season.get('summary', '')),
                        'episodes': copy.deepcopy(season['episodes']),
                    })
            show_dict['seasons'] = season_data
        return show_data
    except Exception as e:
        logger.error(f"Exception:{e} [site={site} code={site_code}]")
        logger.error(traceback.format_exc())
