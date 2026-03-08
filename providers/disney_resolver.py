import re
import traceback
from html import unescape

import requests

from ..providers.legacy_registry import get_ottcode_class
from ..setup import P
from ..services.code_service import sort_code
from ..services.provider_service import get_show_data

logger = P.logger
OTTCODE = get_ottcode_class()

DISNEY_HEADERS = {
    "sec-ch-ua-platform": "\"Windows\"",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "sec-ch-ua": "\"Google Chrome\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
    "Content-Type": "text/plain;charset=UTF-8",
    "Origin": "https://www.disneyplus.com",
    "Referer": "https://www.disneyplus.com/",
}
DISNEY_PAGE_LOCALES = ('ko-kr', 'en-kr')


def is_disney_entity_code(code):
    code = re.sub(r'^entity-', '', code.strip())
    return re.match(r'^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$', code) is not None


def extract_page_metadata(html):
    title = ''
    description = ''
    year = ''
    patterns = [
        (r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', 'title'),
        (r'<meta[^>]+name=["\']title["\'][^>]+content=["\']([^"\']+)', 'title'),
        (r'<title>([^<]+)</title>', 'title'),
        (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)', 'description'),
        (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', 'description'),
        (r'\"datePublished\":\"(\d{4})\"', 'year'),
        (r'\"releaseYear\":\"(\d{4})\"', 'year'),
    ]
    for pattern, key in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            value = unescape(match.group(1)).strip()
            if key == 'title' and not title:
                title = value
            elif key == 'description' and not description:
                description = value
            elif key == 'year' and not year:
                year = value
    return title, description, year


def normalize_title(title):
    title = unescape(title).strip()
    title = re.sub(r'\s*\|\s*디즈니\+.*$', '', title)
    title = re.sub(r'\s*\|\s*Disney\+.*$', '', title)
    title = re.sub(r'^Watch\s+', '', title)
    return title.strip()


def title_key(title):
    title = normalize_title(title)
    return re.sub(r'[^0-9A-Za-z가-힣]+', '', title).lower()


def build_title_variants(title):
    variants = []
    normalized = normalize_title(title)
    if normalized:
        variants.append(normalized)
        variants.append(re.sub(r'(?<=[가-힣A-Za-z])(?=\d)', ' ', normalized))
        variants.append(re.sub(r'(?<=\d)(?=[가-힣A-Za-z])', ' ', normalized))
        variants.append(re.sub(r'\s+', ' ', normalized).strip())
    unique = []
    for candidate in variants:
        candidate = candidate.strip()
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def build_title_candidates(titles):
    if isinstance(titles, str):
        titles = [titles]
    candidates = []
    seen = set()
    for title in titles or []:
        for variant in build_title_variants(title):
            key = title_key(variant)
            if key and key not in seen:
                candidates.append(variant)
                seen.add(key)
    return candidates


def resolve_candidate_code(titles, year):
    variants = build_title_candidates(titles)
    if not variants or OTTCODE is None:
        return None, None
    for variant in variants:
        for use_year in [True, False]:
            if use_year and not year:
                continue
            ottcode = OTTCODE(variant, year) if use_year else OTTCODE(variant)
            ottcode_list = ottcode.get_ott_code()
            logger.debug(f"DSNP HTML metadata OTT search variant={variant} year={year if use_year else ''} count={len(ottcode_list) if ottcode_list else 0}")
            resolved = sort_code(['DSNP'], ottcode_list)
            logger.debug(f"DSNP HTML metadata resolved candidate={resolved} variant={variant}")
            if resolved and resolved.startswith('FD'):
                return resolved, variant
    return None, None


def extract_build_id(html):
    patterns = [
        r'/_next/data/([^/]+)/',
        r'"buildId":"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ''


def make_entity_url(entity_code, locale='ko-kr'):
    entity_code = re.sub(r'^entity-', '', entity_code.strip())
    return f'https://www.disneyplus.com/{locale}/browse/entity-{entity_code}'


def fetch_page(url):
    try:
        response = requests.get(url, headers=DISNEY_HEADERS, allow_redirects=True, timeout=10)
        return response
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
        return None


def fetch_next_data_titles(entity_code, html):
    build_id = extract_build_id(html)
    if not build_id:
        return []
    titles = []
    for locale in DISNEY_PAGE_LOCALES:
        next_url = f'https://www.disneyplus.com/_next/data/{build_id}/{locale}/browse/entity-{entity_code}.json'
        try:
            response = requests.get(next_url, headers=DISNEY_HEADERS, allow_redirects=True, timeout=10)
            if not response.ok:
                logger.debug(f"DSNP next data fetch miss locale={locale} status={response.status_code}")
                continue
            title, _, _ = extract_page_metadata(response.text)
            normalized_title = normalize_title(title)
            logger.debug(f"DSNP next data locale={locale} title={normalized_title}")
            if normalized_title:
                titles.append(normalized_title)
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
    return titles


def collect_page_metadata_titles(fallback_code, primary_response):
    titles = []
    years = []
    responses = []
    if primary_response is not None:
        responses.append(('primary', primary_response))

    for locale in DISNEY_PAGE_LOCALES:
        locale_url = make_entity_url(fallback_code, locale)
        if primary_response is not None and primary_response.url.split('?', 1)[0] == locale_url:
            continue
        response = fetch_page(locale_url)
        if response is not None:
            responses.append((locale, response))

    for source, response in responses:
        title, description, year = extract_page_metadata(response.text)
        normalized_title = normalize_title(title)
        logger.debug(
            f"DSNP metadata source={source} final_url={response.url.split('?', 1)[0]} "
            f"title={normalized_title} year={year} description_len={len(description)} fallback_code={fallback_code}"
        )
        if normalized_title:
            titles.append(normalized_title)
        if year:
            years.append(year)
        for next_title in fetch_next_data_titles(fallback_code, response.text):
            if next_title:
                titles.append(next_title)

    unique_titles = []
    seen_titles = set()
    for title in titles:
        key = title_key(title)
        if key and key not in seen_titles:
            unique_titles.append(title)
            seen_titles.add(key)
    year = years[0] if years else ''
    return unique_titles, year


def resolve_code_from_titles(titles, year, fallback_code):
    logger.debug(f"DSNP title candidates={titles} year={year} fallback_code={fallback_code}")
    if not titles:
        return None
    try:
        resolved, matched_title = resolve_candidate_code(titles, year)
        if resolved and resolved.startswith('FD'):
            show_data = get_show_data(resolved)
            expected_key = title_key(matched_title or titles[0])
            candidate_titles = []
            if isinstance(show_data, dict):
                candidate_titles.extend([
                    show_data.get('title', ''),
                    show_data.get('original_title', ''),
                    show_data.get('title_sort', ''),
                ])
            candidate_keys = [title_key(x) for x in candidate_titles if x]
            logger.debug(f"DSNP HTML metadata candidate_keys={candidate_keys} expected_key={expected_key}")
            if expected_key and expected_key in candidate_keys:
                return resolved[2:]
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    return None


def resolve_code_from_page_sources(primary_response, fallback_code):
    titles, year = collect_page_metadata_titles(fallback_code, primary_response)
    return resolve_code_from_titles(titles, year, fallback_code)


def resolve_input(code):
    code = code.strip()
    fallback_code = code
    request_url = ''
    logger.debug(f"DSNP redirect start raw={code}")
    if 'disneyplus.com' in code:
        url = code
        request_url = url.split('?', 1)[0]
        match = re.search(r'/series/.*?/(?P<code>[^?&#/]+)', code)
        if match:
            logger.debug(f"DSNP redirect direct series code={match.group('code')}")
            return match.group('code')
        match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', code)
        if match:
            fallback_code = match.group('code').replace('entity-', '', 1)
    else:
        fallback_code = re.sub(r'^entity-', '', code)
        url = 'https://www.disneyplus.com/ko-kr/browse/entity-' + fallback_code
        request_url = url
    logger.debug(f"DSNP redirect prepared fallback={fallback_code} request_url={request_url}")

    try:
        response = requests.get(url, headers=DISNEY_HEADERS, allow_redirects=True, timeout=10)
        logger.debug(f"DSNP redirect response final_url={response.url.split('?', 1)[0]} history={len(response.history)}")
        match = re.search(r'disneyplus\.com(\/ko-kr)?\/series\/.*?\/(?P<code>[^?=&/]+)', response.url)
        if match:
            logger.debug(f"DSNP redirect resolved series code={match.group('code')}")
            return match.group('code')
        match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', response.url)
        if match:
            browse_code = match.group('code').replace('entity-', '', 1)
            logger.debug(f"DSNP redirect browse fallback code={browse_code}")
            resolved_code = resolve_code_from_page_sources(response, browse_code)
            if resolved_code:
                logger.debug(f"DSNP redirect resolved code from metadata={resolved_code}")
                return resolved_code
            return browse_code
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    logger.debug(f"DSNP redirect returning fallback={fallback_code}")
    return fallback_code
