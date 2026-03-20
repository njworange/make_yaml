import copy
import html
import importlib
import json
import re
import traceback
from datetime import datetime
from html.parser import HTMLParser

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
PRIME_VIDEO_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}
NETFLIX_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}
APPLE_TV_UTS_PARAMS = {
    'caller': 'web',
    'includeSeasonSummary': 'false',
    'locale': 'ko-KR',
    'pfm': 'web',
    'selectedSeasonEpisodesOnly': 'false',
    'sf': '143466',
    'utscf': 'OjAAAAEAAAAAAAMAEAAAACMAKwAtAC8A',
    'utsk': '6e3013c6d6fae3c2::::::00b164cc451c7be6',
    'v': '92',
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


def extract_prime_detail_code(value):
    text = str(value or '').strip()
    match = re.search(r'primevideo\.com\/(?:-\/[^/]+\/)?detail(?:\/[^/]+)?\/(?P<code>[A-Z0-9]{10,})', text)
    if match:
        return match.group('code')
    match = re.search(r'(?P<code>[A-Z0-9]{10,})', text)
    if match:
        return match.group('code')
    return text


def extract_netflix_title_code(value):
    text = str(value or '').strip()
    match = re.search(r'netflix\.com\/(?:(?:[a-z]{2}(?:-[a-z]{2})?)\/)?title\/(?P<code>[^/#?]+)', text, flags=re.I)
    if match:
        return match.group('code')
    match = re.search(r'(?P<code>\d{6,})', text)
    if match:
        return match.group('code')
    return text


def decode_ebs_text(value):
    text = html.unescape(str(value or ''))
    text = text.replace('&nbsp;', ' ')
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text.replace('\xa0', ' '))
    return text.strip()


def decode_response_html(response):
    content = response.content or b''
    for encoding in ['utf-8', response.encoding, getattr(response, 'apparent_encoding', None), 'cp949']:
        if not encoding:
            continue
        try:
            return content.decode(encoding)
        except Exception:
            continue
    return response.text


def fetch_ebs_html(url):
    response = requests.get(url, headers=EBS_HEADERS, timeout=15)
    response.raise_for_status()
    return decode_response_html(response)


def post_ebs_html(url, data=None):
    response = requests.post(url, headers=EBS_HEADERS, data=data or {}, timeout=15)
    response.raise_for_status()
    return decode_response_html(response)


def fetch_appletv_html(url):
    response = requests.get(url, headers=APPLE_TV_HEADERS, timeout=15)
    response.raise_for_status()
    return decode_response_html(response)


def fetch_prime_html(url):
    response = requests.get(url, headers=PRIME_VIDEO_HEADERS, timeout=15)
    response.raise_for_status()
    return decode_response_html(response)


def fetch_netflix_html(url):
    response = requests.get(url, headers=NETFLIX_HEADERS, timeout=15)
    response.raise_for_status()
    return decode_response_html(response)


def fetch_appletv_json(url, params=None):
    response = requests.get(url, headers=APPLE_TV_HEADERS, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


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
    title = re.sub(r'^20\d{2}\.\d{2}\.\d{2}\([월화수목금토일]\)\s*', '', title)
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
        r'<a\s+href="(?P<href>/vodCommon/show\?[^"]*siteCd=AK[^"]*)".*?'
        r'<img\s+src="(?P<thumb>[^"]*)".*?'
        r'<p>(?P<title>.*?)</p>\s*<span>(?P<date>[^<]+)</span>',
        flags=re.S,
    )
    seen_lect_ids = set()
    for match in pattern.finditer(page_html):
        href = html.unescape(match.group('href').strip())
        lect_id_match = re.search(r'[?&]lectId=([^&"]+)', href)
        lect_id = lect_id_match.group(1).strip() if lect_id_match else ''
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
            '_detail_path': href,
        })
    return episodes


def extract_ebs_ajax_episodes(page_html):
    episodes = []
    pattern = re.compile(
        r'<div\s+class="item">.*?'
        r'<a\s+href="(?P<href>/vodCommon/show\?[^\"]*lectId=(?P<lect_id>[^&\"]+)[^\"]*)"[^>]*>.*?'
        r'<img[^>]+src="(?P<thumb>[^\"]*)".*?</a>.*?'
        r'<dt\s+class="vod_title">(?P<title>.*?)</dt>.*?'
        r'<dd\s+class="vod_disk">(?P<summary>.*?)</dd>.*?'
        r'<li\s+class="vod_date">\s*<span>(?P<date>[^<]+)</span>',
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
        summary = decode_ebs_text(re.sub(r'<[^>]+>', ' ', match.group('summary')))
        summary = re.sub(r'\s+', ' ', summary).strip()
        episodes.append({
            'index': index,
            'title': title,
            'summary': summary,
            'thumbs': match.group('thumb').strip(),
            'originally_available_at': date_text,
            'code': lect_id,
            '_detail_path': html.unescape(match.group('href').strip()),
        })
    return episodes


def fetch_ebs_ajax_episodes(course_id, step_id='', orderby='OLD', max_pages=20):
    episodes = []
    seen_codes = set()
    for page_number in range(1, max_pages + 1):
        ajax_html = post_ebs_html(
            'https://anikids.ebs.co.kr/anikids/getVodListAjax',
            data={
                'pageNumber': page_number,
                'courseId': course_id,
                'stepId': step_id,
                'orderby': orderby,
            },
        )
        page_episodes = extract_ebs_ajax_episodes(ajax_html)
        if not page_episodes:
            break
        added_count = 0
        for episode in page_episodes:
            if episode['code'] in seen_codes:
                continue
            seen_codes.add(episode['code'])
            episode['index'] = len(episodes) + 1
            episodes.append(episode)
            added_count += 1
        if added_count == 0:
            break
        if "paginationAK('" not in ajax_html:
            break
    return episodes


def extract_ebs_episode_summary(page_html):
    body_match = re.search(r'<dd[^>]+class=["\']vod_disk["\'][^>]*>(?P<summary>.*?)</dd>', page_html, flags=re.S | re.I)
    if body_match:
        summary = decode_ebs_text(re.sub(r'<[^>]+>', ' ', body_match.group('summary')))
        summary = re.sub(r'\s+', ' ', summary).strip()
        if summary:
            return summary
    script_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>\s*(?P<json>.*?)\s*</script>',
        flags=re.S | re.I,
    )
    for match in script_pattern.finditer(page_html):
        try:
            payload = json.loads(match.group('json'))
        except Exception:
            continue
        candidates = []
        if isinstance(payload, list):
            candidates.extend(payload)
        elif isinstance(payload, dict):
            candidates.append(payload)
            graph = payload.get('@graph')
            if isinstance(graph, list):
                candidates.extend(graph)
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_type = candidate.get('@type')
            candidate_types = candidate_type if isinstance(candidate_type, list) else [candidate_type]
            if 'VideoObject' not in candidate_types:
                continue
            summary = decode_ebs_text(candidate.get('description') or '')
            if summary:
                return summary
    return ''


def enrich_ebs_episode(episode):
    detail_path = episode.get('_detail_path') or ''
    if detail_path and not episode.get('summary'):
        try:
            detail_html = fetch_ebs_html(f'https://anikids.ebs.co.kr{detail_path}')
            summary = extract_ebs_episode_summary(detail_html)
            if summary:
                episode['summary'] = summary
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
    original_title = normalize_ebs_episode_title(episode.get('title', ''))
    date_prefix = format_korean_broadcast_date(episode.get('originally_available_at', ''))
    if date_prefix and original_title:
        episode['title'] = f'{date_prefix} {original_title}'
    elif original_title:
        episode['title'] = original_title
    episode.pop('_detail_path', None)
    return episode


def sanitize_ebs_episode_summaries(episodes):
    if not episodes:
        return episodes
    seen_summaries = {}
    for episode in episodes:
        summary = (episode.get('summary') or '').strip()
        if not summary:
            continue
        seen_summaries.setdefault(summary, []).append(episode)
    for summary, grouped_episodes in seen_summaries.items():
        if len(grouped_episodes) < 2:
            continue
        first_episode = grouped_episodes[0]
        for episode in grouped_episodes[1:]:
            if episode.get('code') != first_episode.get('code'):
                episode['summary'] = ''
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
        step_id = season_entry['step_id'] or str(vod_option.get('stepId') or '').strip()
        episodes = fetch_ebs_ajax_episodes(course_id, step_id) if step_id else []
        if not episodes:
            episodes = extract_ebs_episodes(season_html)
        if not episodes:
            continue
        episodes = [enrich_ebs_episode(episode) for episode in episodes]
        episodes = sanitize_ebs_episode_summaries(episodes)
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


def extract_prime_meta_content(page_html, property_name):
    pattern = re.compile(r'<meta\b[^>]*>', flags=re.I | re.S)
    name_pattern = re.compile(r'(?:property|name)=["\'](?P<key>.*?)["\']', flags=re.I | re.S)
    content_pattern = re.compile(r'content=["\'](?P<value>.*?)["\']', flags=re.I | re.S)
    for tag in pattern.finditer(page_html):
        meta_tag = tag.group(0)
        key_match = name_pattern.search(meta_tag)
        content_match = content_pattern.search(meta_tag)
        if not key_match or not content_match:
            continue
        if key_match.group('key').strip().lower() != property_name.lower():
            continue
        return decode_ebs_text(content_match.group('value'))
    return ''


def extract_prime_title(page_html):
    candidates = []
    title_match = re.search(r'<title>(?P<value>.*?)</title>', page_html, flags=re.I | re.S)
    if title_match:
        candidates.append(decode_ebs_text(title_match.group('value')))
    candidates.append(extract_prime_meta_content(page_html, 'title'))
    candidates.append(extract_prime_meta_content(page_html, 'og:title'))
    for candidate in candidates:
        title = candidate.strip()
        if not title:
            continue
        title = re.sub(r'^(?:Prime Video|프라임 비디오):\s*', '', title)
        title = re.sub(r'\s*-\s*(?:Season|시즌)\s*\d+\s*$', '', title, flags=re.I)
        title = re.sub(r'\s+(?:Season|시즌)\s*\d+\s*-\s*프라임 비디오.*$', '', title, flags=re.I)
        title = re.sub(r'\s*-\s*Prime Video.*$', '', title, flags=re.I)
        title = re.sub(r'\s*-\s*프라임 비디오.*$', '', title, flags=re.I)
        title = title.strip()
        if title:
            return title
    return ''


def extract_prime_season_index(page_html):
    title_match = re.search(r'<title>(?P<value>.*?)</title>', page_html, flags=re.I | re.S)
    title_text = decode_ebs_text(title_match.group('value')) if title_match else ''
    for pattern in [r'(?:Season|시즌)\s*(\d+)', r'시즌\s*(\d+)']:
        match = re.search(pattern, title_text, flags=re.I)
        if match:
            return int(match.group(1))
    return 1


def normalize_prime_date(date_text):
    text = decode_ebs_text(date_text)
    match = re.search(r'(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return ''


def normalize_prime_duration(duration_text):
    text = decode_ebs_text(duration_text)
    hour_match = re.search(r'(\d+)시간', text)
    minute_match = re.search(r'(\d+)분', text)
    hours = int(hour_match.group(1)) if hour_match else 0
    minutes = int(minute_match.group(1)) if minute_match else 0
    return hours * 60 + minutes


def extract_prime_text(page_html):
    text = html.unescape(str(page_html or ''))
    text = re.sub(r'(?is)<script\b[^>]*>.*?</script>', ' ', text)
    text = re.sub(r'(?is)<style\b[^>]*>.*?</style>', ' ', text)
    text = re.sub(r'(?is)<noscript\b[^>]*>.*?</noscript>', ' ', text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(?:p|div|section|article|main|aside|header|footer|ul|ol|li|h1|h2|h3|h4|h5|h6|button)>', '\n', text)
    text = re.sub(r'(?i)<[^>]+>', ' ', text)
    text = text.replace('\r', '')
    lines = []
    for raw_line in text.split('\n'):
        line = re.sub(r'\s+', ' ', raw_line.replace('\xa0', ' ')).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


def normalize_prime_episode_title(title):
    text = decode_ebs_text(title)
    text = re.sub(r'^시즌\s*\d+\s*에피소드\s*\d+\s*-\s*', '', text)
    text = re.sub(r'^20\d{2}\.\d{2}\.\d{2}\([월화수목금토일]\)\s*', '', text)
    return text.strip()


def extract_prime_episodes(page_html):
    page_text = extract_prime_text(page_html)
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    episodes = []
    season_index = None
    label_pattern = re.compile(r'^시즌\s*(?P<season>\d+)\s*에피소드\s*(?P<index>\d+)\s*-\s*(?P<title>.+)$')
    date_pattern = re.compile(r'^20\d{2}년\s*\d{1,2}월\s*\d{1,2}일$')
    runtime_pattern = re.compile(r'^(?:\d+시간\s*\d+분|\d+시간|\d+분)$')
    stop_lines = {
        '에피소드', '탐색', '기타', '연관 내용', '세부 정보', '고객들이 시청한 다른 작품',
        '세부 정보 정보 더 보기', '콘텐츠 설명이 프로그램에는 간접 광고가 포함되어 있습니다, 점멸 표시 등, Flashing lights and strobing patterns might affect photosensitive viewers',
    }
    noise_lines = {
        'Store Filled', '프라임 가입하기', 'Store Filled프라임 가입하기', '프라임으로 보기',
        'Add', '워치리스트', '좋아요', '마음에 들지 않음', 'Share Android', '공유하기',
        '정렬', '최신 에피소드', '에피소드 번호',
    }
    i = 0
    while i < len(lines):
        label_match = label_pattern.match(lines[i])
        if not label_match:
            i += 1
            continue
        season_value = int(label_match.group('season'))
        episode_index = int(label_match.group('index'))
        title = normalize_prime_episode_title(lines[i])
        if season_index is None:
            season_index = season_value
        air_date = ''
        summary_lines = []
        j = i + 1
        if j < len(lines) and date_pattern.match(lines[j]):
            air_date = normalize_prime_date(lines[j])
            j += 1
        if j < len(lines) and runtime_pattern.match(lines[j]):
            j += 1
        if j < len(lines) and (re.match(r'^(전체|\d+\+|PG|TV-|15|18|7\+)', lines[j]) or '등급' in lines[j]):
            j += 1
        while j < len(lines):
            if label_pattern.match(lines[j]):
                break
            if lines[j] in stop_lines:
                break
            if lines[j] not in noise_lines:
                summary_lines.append(lines[j])
            j += 1
        episodes.append({
            'index': episode_index,
            'title': f"{format_korean_broadcast_date(air_date)} {title}" if air_date and title else title,
            'summary': decode_ebs_text(' '.join(summary_lines)),
            'originally_available_at': air_date,
        })
        i = j
    return {
        'season_index': season_index,
        'episodes': episodes,
    }


def build_prime_show_data(detail_code):
    detail_code = extract_prime_detail_code(detail_code)
    if not detail_code:
        return None
    page_html = fetch_prime_html(f'https://www.primevideo.com/-/ko/detail/{detail_code}')
    title = extract_prime_title(page_html)
    summary = extract_prime_meta_content(page_html, 'description')
    thumb = extract_prime_meta_content(page_html, 'og:image')
    episode_payload = extract_prime_episodes(page_html)
    episodes = episode_payload.get('episodes') or []
    season_index = episode_payload.get('season_index') or extract_prime_season_index(page_html)
    if not title or not summary or not episodes:
        return None
    show_data = {
        'title': title,
        'summary': summary,
        'seasons': [],
    }
    season = {
        'index': season_index,
        'title': f'시즌 {season_index}',
        'summary': '',
        'episodes': episodes,
    }
    if thumb:
        for episode in season['episodes']:
            episode['thumbs'] = thumb
    show_data['seasons'] = [season]
    air_dates = [episode.get('originally_available_at') for episode in episodes if episode.get('originally_available_at')]
    if air_dates:
        show_data['originally_available_at'] = min(air_dates)
    return show_data


def extract_netflix_meta_content(page_html, property_name):
    pattern = re.compile(r'<meta\b[^>]*>', flags=re.I | re.S)
    name_pattern = re.compile(r'(?:property|name)=["\'](?P<key>.*?)["\']', flags=re.I | re.S)
    content_pattern = re.compile(r'content=["\'](?P<value>.*?)["\']', flags=re.I | re.S)
    for tag in pattern.finditer(page_html):
        meta_tag = tag.group(0)
        key_match = name_pattern.search(meta_tag)
        content_match = content_pattern.search(meta_tag)
        if not key_match or not content_match:
            continue
        if key_match.group('key').strip().lower() != property_name.lower():
            continue
        return decode_ebs_text(content_match.group('value'))
    return ''


def extract_netflix_title(page_html):
    candidates = []
    title_match = re.search(r'<title>(?P<value>.*?)</title>', page_html, flags=re.I | re.S)
    if title_match:
        candidates.append(decode_ebs_text(title_match.group('value')))
    candidates.append(extract_netflix_meta_content(page_html, 'og:title'))
    for candidate in candidates:
        title = candidate.strip()
        if not title:
            continue
        title = re.sub(r',\s*지금 시청하세요\s*\|\s*넷플릭스 공식 사이트$', '', title)
        title = re.sub(r'\|\s*넷플릭스 공식 사이트$', '', title)
        title = re.sub(r',\s*Watch Now\s*\|\s*Netflix Official Site$', '', title, flags=re.I)
        title = re.sub(r'\|\s*Netflix Official Site$', '', title, flags=re.I)
        title = title.strip()
        if title:
            return title
    return ''


def extract_netflix_text(page_html):
    text = html.unescape(str(page_html or ''))
    text = re.sub(r'(?is)<script\b[^>]*>.*?</script>', ' ', text)
    text = re.sub(r'(?is)<style\b[^>]*>.*?</style>', ' ', text)
    text = re.sub(r'(?is)<noscript\b[^>]*>.*?</noscript>', ' ', text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(?:p|div|section|article|main|aside|header|footer|ul|ol|li|h1|h2|h3|h4|h5|h6|button|a)>', '\n', text)
    text = re.sub(r'(?i)<[^>]+>', ' ', text)
    text = text.replace('\r', '')
    lines = []
    for raw_line in text.split('\n'):
        line = re.sub(r'\s+', ' ', raw_line.replace('\xa0', ' ')).strip()
        if line:
            lines.append(line)
    return lines


def normalize_netflix_episode_title(title):
    text = decode_ebs_text(title)
    text = re.sub(r'^\d+\.\s*', '', text)
    text = re.sub(r'^20\d{2}\.\d{2}\.\d{2}\([월화수목금토일]\)\s*', '', text)
    return text.strip()


def split_netflix_people(value):
    text = decode_ebs_text(value)
    if ':' in text:
        text = text.split(':', 1)[1]
    return [item.strip() for item in re.split(r',| 및 ', text) if item.strip()]


def extract_netflix_declared_episode_count(lines):
    for line in lines:
        match = re.search(r'에피소드\s*(\d+)개', line)
        if match:
            return int(match.group(1))
        match = re.search(r'(\d+)\s+Episodes', line, flags=re.I)
        if match:
            return int(match.group(1))
    return 0


def extract_netflix_extras(lines):
    extras = {}
    actors = []
    creators = []
    genres = []
    for index, line in enumerate(lines):
        if line.startswith('출연:') or line.startswith('Starring:'):
            actors = split_netflix_people(line)
        elif line.startswith('크리에이터:') or line.startswith('Creators:'):
            creators = split_netflix_people(line)
        elif line == '장르' and index + 1 < len(lines):
            genres = [item.strip() for item in re.split(r',| 및 ', lines[index + 1]) if item.strip()]
    if actors:
        extras['actors'] = actors
    if creators:
        extras['creators'] = creators
    if genres:
        extras['genres'] = genres
    return extras


class NetflixEpisodeHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.episodes_depth = None
        self.episodes_tag = None
        self.current_item = None
        self.current_li_depth = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if self.episodes_depth is None and attr_map.get('id') == 'episodes':
            self.episodes_depth = self.depth
            self.episodes_tag = tag
        if self.episodes_depth is not None and self.current_item is None and tag == 'li':
            self.current_item = {'thumbs': '', 'texts': []}
            self.current_li_depth = self.depth
        if self.current_item is not None and tag == 'img' and not self.current_item['thumbs']:
            self.current_item['thumbs'] = attr_map.get('src') or attr_map.get('data-src') or ''
        self.depth += 1

    def handle_endtag(self, tag):
        self.depth -= 1
        if self.current_item is not None and tag == 'li' and self.depth == self.current_li_depth:
            self.items.append(self.current_item)
            self.current_item = None
            self.current_li_depth = None
        if self.episodes_depth is not None and tag == self.episodes_tag and self.depth == self.episodes_depth:
            self.episodes_depth = None
            self.episodes_tag = None

    def handle_data(self, data):
        if self.current_item is None:
            return
        text = re.sub(r'\s+', ' ', data.replace('\xa0', ' ')).strip()
        if text:
            self.current_item['texts'].append(text)


def extract_netflix_episode_cards(page_html):
    parser = NetflixEpisodeHTMLParser()
    parser.feed(page_html)
    runtime_pattern = re.compile(r'^(?:\d+분|\d+시간(?:\s*\d+분)?)$')
    title_pattern = re.compile(r'^\d+\.\s+.+$')
    episodes = []
    for item in parser.items:
        texts = []
        for text in item.get('texts', []):
            if not texts or texts[-1] != text:
                texts.append(text)
        if len(texts) < 3 or not runtime_pattern.match(texts[0]) or not title_pattern.match(texts[1]):
            continue
        episode_index_match = re.match(r'^(?P<index>\d+)\.', texts[1])
        episode_index = int(episode_index_match.group('index')) if episode_index_match else len(episodes) + 1
        episodes.append({
            'index': episode_index,
            'title': normalize_netflix_episode_title(texts[1]),
            'summary': decode_ebs_text(' '.join(texts[2:])),
            'thumbs': item.get('thumbs', ''),
        })
    return episodes


def extract_netflix_episode_blocks(lines):
    episodes = []
    runtime_pattern = re.compile(r'^(?:\d+분|\d+시간(?:\s*\d+분)?)$')
    title_pattern = re.compile(r'^\d+\.\s+.+$')
    stop_lines = {
        '상세 정보 보기', 'More Details', '회원님이 좋아하실 만한 콘텐츠', 'You Might Also Like',
        '지금 뜨는 콘텐츠', 'Trending Now', '나의 니즈에 꼭 맞는 멤버십', 'A Plan To Suit Your Needs',
    }
    in_episode_section = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line in {'회차', 'Episodes'}:
            in_episode_section = True
            i += 1
            continue
        if not in_episode_section:
            i += 1
            continue
        if line in stop_lines:
            break
        if not runtime_pattern.match(line):
            i += 1
            continue
        if i + 1 >= len(lines) or not title_pattern.match(lines[i + 1]):
            i += 1
            continue
        runtime_line = line
        title_line = lines[i + 1]
        summary_lines = []
        j = i + 2
        while j < len(lines):
            if lines[j] in stop_lines:
                break
            if runtime_pattern.match(lines[j]) and j + 1 < len(lines) and title_pattern.match(lines[j + 1]):
                break
            summary_lines.append(lines[j])
            j += 1
        episode_index_match = re.match(r'^(?P<index>\d+)\.', title_line)
        episode_index = int(episode_index_match.group('index')) if episode_index_match else len(episodes) + 1
        episodes.append({
            'index': episode_index,
            'title': normalize_netflix_episode_title(title_line),
            'summary': decode_ebs_text(' '.join(summary_lines)),
        })
        i = j
    return episodes


def has_reliable_netflix_episodes(episodes):
    if not episodes:
        return False
    forbidden_tokens = ['상세 정보 보기', '회원님이 좋아하실 만한 콘텐츠', '지금 뜨는 콘텐츠', '나의 니즈에 꼭 맞는 멤버십']
    for episode in episodes:
        title = (episode.get('title') or '').strip()
        summary = (episode.get('summary') or '').strip()
        if not title or not summary:
            return False
        if any(token in summary for token in forbidden_tokens):
            return False
    return True


def build_netflix_show_data(title_code):
    title_code = extract_netflix_title_code(title_code)
    page_html = fetch_netflix_html(f'https://www.netflix.com/kr/title/{title_code}')
    title = extract_netflix_title(page_html)
    summary = extract_netflix_meta_content(page_html, 'og:description') or extract_netflix_meta_content(page_html, 'description')
    poster = extract_netflix_meta_content(page_html, 'og:image')
    lines = extract_netflix_text(page_html)
    declared_episode_count = extract_netflix_declared_episode_count(lines)
    episodes = extract_netflix_episode_cards(page_html)
    if not has_reliable_netflix_episodes(episodes):
        episodes = extract_netflix_episode_blocks(lines)
    if declared_episode_count and len(episodes) < declared_episode_count:
        logger.debug(
            f"Netflix public parse incomplete code={title_code} declared={declared_episode_count} parsed={len(episodes)}"
        )
        return None
    if not title or not summary or not has_reliable_netflix_episodes(episodes):
        return None
    show_data = {
        'title': title,
        'summary': summary,
        'seasons': [{
            'index': 1,
            'title': '시즌 1',
            'summary': '',
            'episodes': episodes,
        }],
    }
    extras = extract_netflix_extras(lines)
    if extras:
        show_data['extras'] = extras
    if poster:
        show_data['posters'] = [poster]
        for episode in show_data['seasons'][0]['episodes']:
            episode.setdefault('thumbs', poster)
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


def normalize_appletv_date(value):
    text = decode_ebs_text(value)
    match = re.search(r'(20\d{2})-(\d{2})-(\d{2})', text)
    if match:
        return f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
    text = str(value or '').strip()
    if text.isdigit():
        try:
            return datetime.utcfromtimestamp(int(text) / 1000).strftime('%Y-%m-%d')
        except Exception:
            return ''
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(value) / 1000).strftime('%Y-%m-%d')
        except Exception:
            return ''
    return ''


def extract_appletv_src_from_srcset(srcset):
    candidates = []
    for part in str(srcset or '').split(','):
        token = part.strip().split(' ')[0].strip()
        if token:
            candidates.append(token)
    return candidates[-1] if candidates else ''


def extract_appletv_code_from_url(url):
    match = re.search(r'/(umc\.[a-z]+\.[A-Za-z0-9]+)(?:\?|$)', str(url or ''))
    if match:
        return match.group(1)
    return ''


def normalize_appletv_image_url(image_data):
    if isinstance(image_data, dict):
        template = str(image_data.get('url') or '').strip()
        width = int(image_data.get('width') or 1200)
        height = int(image_data.get('height') or 675)
    else:
        template = str(image_data or '').strip()
        width = 1200
        height = 675
    if not template:
        return ''
    return template.replace('{w}', str(width)).replace('{h}', str(height)).replace('{f}', 'jpg')


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


def extract_appletv_season_titles(page_html):
    titles = []
    seen_titles = set()
    for match in re.finditer(r'<option[^>]*>(?P<title>\s*시즌\s*\d+\s*)</option>', page_html, flags=re.S):
        title = decode_ebs_text(match.group('title'))
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        titles.append(title)
    return titles


def extract_appletv_episodes(season_html):
    episodes = []
    pattern = re.compile(
        r'<a[^>]+href="(?P<href>https://tv\.apple\.com/[^"]+/episode/[^"]+)"[^>]*>.*?'
        r'(?:<source[^>]+srcset="(?P<srcset>[^"]+)"[^>]*>.*?)?'
        r'<div class="tag[^"]*">에피소드\s*(?P<index>\d+)</div>\s*<div class="title[^"]*">(?P<title>.*?)</div>\s*<div class="description[^"]*">(?P<summary>.*?)</div>.*?<div class="duration[^"]*"[^>]*>(?P<duration>.*?)</div>',
        flags=re.S,
    )
    for match in pattern.finditer(season_html):
        episode_url = html.unescape(match.group('href'))
        episodes.append({
            'index': int(match.group('index')),
            'title': decode_ebs_text(match.group('title')),
            'summary': decode_ebs_text(match.group('summary')),
            'thumbs': extract_appletv_src_from_srcset(html.unescape(match.group('srcset') or '')),
            'originally_available_at': '',
            'url': episode_url,
        })
    return episodes


def fetch_appletv_api_episodes(show_id, page_size=10, max_pages=100):
    episodes = []
    seen_codes = set()
    total_episode_count = 0
    for page_index in range(max_pages):
        next_token = f'{page_index * page_size}:{page_size}'
        payload = fetch_appletv_json(
            f'https://tv.apple.com/api/uts/v3/shows/{show_id}/episodes',
            params={**APPLE_TV_UTS_PARAMS, 'nextToken': next_token},
        )
        data = payload.get('data') or {}
        total_episode_count = int(data.get('totalEpisodeCount') or total_episode_count or 0)
        page_episodes = data.get('episodes') or []
        if not page_episodes:
            break
        added_count = 0
        for item in page_episodes:
            episode_code = extract_appletv_code_from_url(item.get('url') or '') or str(item.get('id') or '').strip()
            if not episode_code or episode_code in seen_codes:
                continue
            seen_codes.add(episode_code)
            added_count += 1
            images = item.get('images') or {}
            episode_url = item.get('url') or ''
            episodes.append({
                'index': int(item.get('episodeNumber') or item.get('episodeIndex') or len(episodes) + 1),
                'title': decode_ebs_text(item.get('title') or ''),
                'summary': decode_ebs_text(item.get('description') or ''),
                'thumbs': normalize_appletv_image_url(images.get('contentImage') or images.get('posterArt') or ''),
                'originally_available_at': normalize_appletv_date(item.get('releaseDate')),
                'url': episode_url,
                'season_number': int(item['seasonNumber']) if item.get('seasonNumber') is not None else 1,
            })
        if added_count == 0:
            break
        if total_episode_count and len(seen_codes) >= total_episode_count:
            break
    return episodes


def build_appletv_seasons_from_api(show_id):
    api_episodes = fetch_appletv_api_episodes(show_id)
    seasons_by_number = {}
    for episode in api_episodes:
        season_number = int(episode.pop('season_number', 1) or 1)
        season = seasons_by_number.setdefault(season_number, {
            'index': season_number,
            'title': f'시즌 {season_number}',
            'summary': '',
            'episodes': [],
        })
        season['episodes'].append(episode)
    seasons = []
    for season_number in sorted(seasons_by_number):
        season = seasons_by_number[season_number]
        season['episodes'] = [
            enrich_appletv_episode(episode)
            for episode in sorted(season['episodes'], key=lambda item: item.get('index', 0))
        ]
        seasons.append(season)
    return seasons


def enrich_appletv_episode(episode):
    episode_url = episode.get('url') or ''
    if not episode_url:
        return episode
    try:
        episode_html = fetch_appletv_html(episode_url)
        episode_schema = extract_appletv_json_ld(episode_html, 'schema:tv-episode')
        air_date = normalize_appletv_date(episode_schema.get('datePublished') or '')
        if air_date:
            episode['originally_available_at'] = air_date
        if not episode.get('thumbs'):
            image_url = decode_ebs_text(episode_schema.get('image') or '')
            if image_url:
                episode['thumbs'] = image_url
        original_title = re.sub(r'^20\d{2}\.\d{2}\.\d{2}\([월화수목금토일]\)\s*', '', (episode.get('title') or '').strip())
        date_prefix = format_korean_broadcast_date(episode.get('originally_available_at', ''))
        if date_prefix and original_title:
            episode['title'] = f'{date_prefix} {original_title}'
        elif original_title:
            episode['title'] = original_title
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    finally:
        episode.pop('url', None)
    return episode


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
    season_titles = extract_appletv_season_titles(page_html)
    season_blocks = extract_appletv_season_blocks(page_html)
    seasons = []
    try:
        seasons = build_appletv_seasons_from_api(show_id)
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    for season_title, season_body in season_blocks:
        if seasons:
            break
        season_number_match = re.search(r'(\d+)', season_title)
        season_index = int(season_number_match.group(1)) if season_number_match else len(seasons) + 1
        episodes = extract_appletv_episodes(season_body)
        if not episodes:
            continue
        episodes = [enrich_appletv_episode(episode) for episode in episodes]
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
            current_episodes = [enrich_appletv_episode(episode) for episode in current_episodes]
            season_number_match = re.search(r'(\d+)', current_season_title)
            seasons.append({
                'index': int(season_number_match.group(1)) if season_number_match else 1,
                'title': current_season_title,
                'summary': '',
                'episodes': current_episodes,
            })
    logger.debug(
        f"AppleTV parse show_id={show_id} title={bool(title)} summary={bool(summary)} "
        f"schema={bool(series_schema)} season_titles={len(season_titles)} "
        f"season_blocks={len(season_blocks)} seasons={len(seasons)}"
    )
    if season_titles and len(season_titles) > len(seasons):
        logger.debug(
            f"AppleTV detected additional seasons in selector show_id={show_id} "
            f"selector_titles={season_titles} parsed_seasons={[season.get('title') for season in seasons]}"
        )
    if not seasons:
        if title or summary:
            return {
                'code': show_id,
                'primary': False,
                'title': title or show_id,
                'summary': summary,
                'seasons': [],
            }
        return None
    show_data = {
        'code': show_id,
        'primary': False,
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
        elif site == 'FP':
            site_code = extract_prime_detail_code(site_code)
        elif site == 'FN':
            site_code = extract_netflix_title_code(site_code)
        logger.debug(f"YAMLUTILS get_data parsed site={site} code={site_code}")
        provider_class = get_provider_class(site)
        if provider_class is None and site not in ['KE', 'FA', 'FP', 'FN']:
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
        elif site == 'FP':
            try:
                show_data = build_prime_show_data(site_code)
            except Exception as e:
                logger.error(f"Exception:{str(e)}")
                logger.error(traceback.format_exc())
        elif site == 'FN':
            try:
                show_data = build_netflix_show_data(site_code)
            except Exception as e:
                logger.error(f"Exception:{str(e)}")
                logger.error(traceback.format_exc())
        if show_data in (None, [], ''):
            if site == 'FA':
                logger.debug(f"AppleTV public parse empty; skipping legacy fallback site={site} code={site_code}")
            elif site == 'FP':
                logger.debug(f"Prime public parse empty; falling back to legacy site={site} code={site_code}")
            elif site == 'FN':
                logger.debug(f"Netflix public parse empty; falling back to legacy site={site} code={site_code}")
            if site != 'FA' and provider_class is not None:
                show_data = provider_class.make_data(site_code)
        if site == 'KV':
            show_data = normalize_tving_show_data(show_data)
        elif site == 'KW':
            show_data = normalize_wavve_show_data(site_code, show_data)
        if isinstance(show_data, dict):
            show_data.setdefault('primary', False)
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
