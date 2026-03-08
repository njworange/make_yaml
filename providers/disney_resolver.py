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


def resolve_candidate_code(title, year):
    variants = build_title_variants(title)
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


def resolve_code_from_html(html, fallback_code):
    title, description, year = extract_page_metadata(html)
    normalized_title = normalize_title(title)
    logger.debug(f"DSNP HTML metadata title={normalized_title} year={year} description_len={len(description)} fallback_code={fallback_code}")
    if not normalized_title:
        return None
    try:
        resolved, matched_title = resolve_candidate_code(normalized_title, year)
        if resolved and resolved.startswith('FD'):
            show_data = get_show_data(resolved)
            expected_key = title_key(matched_title or normalized_title)
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

    headers = {
        "sec-ch-ua-platform": "\"Windows\"",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "sec-ch-ua": "\"Google Chrome\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://www.disneyplus.com",
        "Referer": "https://www.disneyplus.com/",
    }
    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        logger.debug(f"DSNP redirect response final_url={response.url.split('?', 1)[0]} history={len(response.history)}")
        match = re.search(r'disneyplus\.com(\/ko-kr)?\/series\/.*?\/(?P<code>[^?=&/]+)', response.url)
        if match:
            logger.debug(f"DSNP redirect resolved series code={match.group('code')}")
            return match.group('code')
        match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', response.url)
        if match:
            browse_code = match.group('code').replace('entity-', '', 1)
            logger.debug(f"DSNP redirect browse fallback code={browse_code}")
            resolved_code = resolve_code_from_html(response.text, browse_code)
            if resolved_code:
                logger.debug(f"DSNP redirect resolved code from HTML={resolved_code}")
                return resolved_code
            return browse_code
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    logger.debug(f"DSNP redirect returning fallback={fallback_code}")
    return fallback_code
