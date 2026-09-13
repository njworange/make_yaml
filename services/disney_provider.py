"""Public Disney entity-page collector; no account API or guessed season fetches."""

import json
import re
from html.parser import HTMLParser

from ..setup import P
from .export_normalizer import normalize_thumb


_UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
_URL = re.compile(
    r'^https?://(?:www\.)?disneyplus\.com/(?:(?P<locale>[a-z]{2}(?:-[a-z]{2})?)/)?'
    r'browse/entity-(?P<id>' + _UUID + r')/?(?:[?#].*)?$', re.I)
_EN_EPISODE = re.compile(r'^S(\d+):E(\d+)(?:\s+(.*))?$', re.S)
_KO_EPISODE = re.compile(r'^시즌\s+(\d+):\s*(\d+)회(?:\s+(.*))?$', re.S)
MAX_SEASONS = 30
MAX_PAGE_SIZE = 5_000_000


def disney_entity_input(value):
    """Return (canonical entity ID, page URL); raw IDs prefer Korean metadata."""
    if not isinstance(value, str):
        return '', ''
    value = value.strip()
    match = _URL.fullmatch(value)
    if match:
        entity_id = match['id'].lower()
        locale = (match['locale'] or 'ko-kr').lower()
    else:
        entity_id = re.sub(r'^entity-', '', value)
        if not re.fullmatch(_UUID, entity_id, re.I):
            return '', ''
        entity_id = entity_id.lower()
        locale = 'ko-kr'
    return entity_id, f'https://www.disneyplus.com/{locale}/browse/entity-{entity_id}'


def uses_disney_public_route(value):
    """Malformed entity inputs must fail here, not invoke opaque legacy code."""
    return isinstance(value, str) and (
        bool(disney_entity_input(value)[0]) or value.startswith('entity-')
        or '/browse/entity-' in value)


class _NextDataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.count = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.inside = True
            self.count += 1

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inside = False


def _text(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('invalid text')
    return value


def _image(variants):
    if variants is None:
        return None
    if not isinstance(variants, dict):
        raise ValueError('invalid image')
    # An actual supplied source has priority. Never confuse episode _id with
    # ripcutId: these identify different things and the former returns 404.
    sizes = ('defaultImage', 'largeImage', 'mediumImage', 'smallImage',
             'xsmallImage', 'xlargeImage', 'xxlargeImage')
    for size in sizes:
        image = variants.get(size)
        if image is None:
            continue
        if not isinstance(image, dict):
            raise ValueError('invalid image variant')
        source = normalize_thumb(image.get('source'))
        if source:
            if not re.match(r'^https?://[^/\s]+/', source):
                raise ValueError('invalid image source')
            return source
    for size in sizes:
        image = variants.get(size) or {}
        ripcut_id = image.get('ripcutId')
        if isinstance(ripcut_id, str) and re.fullmatch(_UUID, ripcut_id, re.I):
            # Template present on the same public page's hero artwork; verified
            # separately with an episode ripcutId (HTTP 200 image/webp).
            return ('https://disney.images.edge.bamgrid.com/ripcut-delivery/v2/variant/'
                    f'disney/{ripcut_id}/compose?format=webp&width=720')
    return None


def parse_disney_show_data(page_html, entity_id):
    """Strict union of selected episodes + SEO seasons, requiring listed coverage.

    Raise ValueError for incomplete/ambiguous data. This does not establish that
    the website publishes every historical episode within a covered season.
    """
    if not isinstance(page_html, str) or len(page_html) > MAX_PAGE_SIZE:
        raise ValueError('invalid page')
    parser = _NextDataParser()
    parser.feed(page_html)
    if parser.count != 1 or parser.inside:
        raise ValueError('missing or duplicate next data')
    payload = json.loads(''.join(parser.parts))
    if payload.get('query', {}).get('slug') != 'entity-' + entity_id:
        raise ValueError('entity mismatch')
    blocks = payload['props']['pageProps']['stitchDocument']['mainContent']
    if not isinstance(blocks, list) or any(not isinstance(b, dict) for b in blocks):
        raise ValueError('invalid blocks')
    candidates = [b for b in blocks if b.get('_type') == 'Episodes']
    if len(candidates) != 1:
        raise ValueError('not an episode series')
    block = candidates[0]
    declared = block.get('seasons')
    if not isinstance(declared, list) or not 1 <= len(declared) <= MAX_SEASONS:
        raise ValueError('missing seasons or cap reached')
    seasons = {}
    numbers = set()
    for entry in declared:
        sid = entry['id']
        name = _text(entry.get('name'))
        match = re.fullmatch(r'(?:Season|시즌)\s+(\d+)', name)
        if not isinstance(sid, str) or not sid or not match or sid in seasons:
            raise ValueError('invalid season identity')
        number = int(match[1])
        if number in numbers:
            raise ValueError('duplicate season number')
        numbers.add(number)
        seasons[sid] = {'index': number, 'title': name, 'episodes': {}}
    seo = block.get('seoSeasons', [])
    if not isinstance(seo, list):
        raise ValueError('invalid SEO seasons')
    bundles = [(entry['seasonId'], entry['episodes']) for entry in seo]
    selected = block.get('episodes', [])
    if not isinstance(selected, list):
        raise ValueError('invalid selected season')
    if selected:
        bundles.append((block.get('selectedSeasonId'), selected))
    seen_ids = {}
    for sid, rows in bundles:
        if sid not in seasons or not isinstance(rows, list):
            raise ValueError('unknown season')
        season = seasons[sid]
        for row in rows:
            title = _text(row.get('title'))
            match = _EN_EPISODE.fullmatch(title) or _KO_EPISODE.fullmatch(title)
            eid = row.get('_id')
            if not match or int(match[1]) != season['index'] or not isinstance(eid, str) or not eid:
                raise ValueError('invalid episode identity')
            index = int(match[2])
            metadata = row.get('metadata') or {}
            episode = {'index': index, 'title': match[3] or '',
                       'summary': _text(metadata.get('summary'))}
            thumb = _image(row.get('imageVariants'))
            if thumb:
                episode['thumbs'] = thumb
            # No date field was established. In particular, release-year ranges
            # in MediaDetails are never episode dates.
            signature = (sid, index, episode)
            if eid in seen_ids and seen_ids[eid] != signature:
                raise ValueError('conflicting duplicate ID')
            prior = season['episodes'].get(index)
            if prior is not None and prior != (eid, episode):
                raise ValueError('conflicting episode number')
            seen_ids[eid] = signature
            season['episodes'][index] = (eid, episode)
    if any(not season['episodes'] for season in seasons.values()):
        raise ValueError('listed seasons not fully represented')
    media = [b for b in blocks if b.get('_type') == 'MediaDetails']
    if len(media) > 1:
        raise ValueError('ambiguous show details')
    media = media[0] if media else {}
    title = _text(media.get('title') or block.get('seriesTitle'))
    if not title.strip():
        raise ValueError('missing show title')
    result = {'primary': False, 'code': 'FD' + entity_id, 'title': title,
              'summary': _text(media.get('summary')), 'seasons': []}
    for season in sorted(seasons.values(), key=lambda item: item['index']):
        result['seasons'].append({'index': season['index'], 'title': season['title'],
                                 'episodes': [pair[1] for _, pair in sorted(season['episodes'].items())]})
    return result


def build_disney_show_data(code, http_get=None):
    try:
        entity_id, url = disney_entity_input(code)
        if not entity_id:
            raise ValueError('invalid entity input')
        if http_get is None:
            import requests
            http_get = requests.get
        response = http_get(url, headers={'User-Agent': 'Mozilla/5.0'},
                            timeout=(5, 15), allow_redirects=False)
        try:
            if response.status_code != 200:
                raise ValueError('HTTP failed')
            return parse_disney_show_data(response.text, entity_id)
        finally:
            response.close()
    except Exception:
        try:
            P.logger.info('DISNEY_PUBLIC reason=UNAVAILABLE_OR_INCOMPLETE')
        except Exception:
            pass
        return None
