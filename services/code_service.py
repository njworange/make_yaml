import re
import traceback

from ..setup import P
from .coupang_provider import COUPANG_URL_PATTERN

logger = P.logger

REGEX_BY_PROVIDER_KEY = {
    'wavve': r'wavve\.com\/player\/(vod\?contentid=|vod\?programid=.*?)(?P<code>[^#][A-Za-z0-9]+_[A-Za-z0-9]+)',
    'tving': r'tving\.(com\/contents)\/(?P<code>[^#].*?)$',
    'coupang': COUPANG_URL_PATTERN,
    'nf': r'netflix\.com\/(?:(?:[a-z]{2}(?:-[a-z]{2})?)\/)?title\/(?P<code>[^/#?]+)',
    'dsnp': r'^https?://(?:www\.)?disneyplus\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:series/[^/]+/(?P<code>[A-Za-z0-9-]+)|browse/entity-(?P<code2>[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}))/?(?:[?#].*)?$',
    'atvp': r'apple.com/.*?(?P<code>umc.cmc.[a-zA-Z0-9]+)$',
    'amzn': r'(?:gti\.(?P<code>[a-zA-Z0-9-]+)|primevideo\.com\/(?:-\/[^/]+\/)?detail(?:\/[^/]+)?\/(?P<code2>[A-Z0-9]{10,}))',
    'ebs': r'anikids\.ebs\.co\.kr\/anikids\/program\/show\/(?P<code>[A-Za-z0-9]+)',
}

PREFIX_BY_PROVIDER_KEY = {
    'wavve': 'KW',
    'tving': 'KV',
    'coupang': 'KC',
    'nf': 'FN',
    'dsnp': 'FD',
    'atvp': 'FA',
    'amzn': 'FP',
    'ebs': 'KE',
}


def sort_code(user_order, url_list):
    if not isinstance(user_order, list):
        try:
            user_order = user_order.split(',')
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
            return None

    try:
        for order in user_order:
            order_key = order.lower().strip()
            regex = REGEX_BY_PROVIDER_KEY.get(order_key)
            prefix = PREFIX_BY_PROVIDER_KEY.get(order_key)
            if regex is None or prefix is None:
                continue
            for url in url_list or []:
                match = re.search(regex, url)
                if match:
                    code = match.groupdict().get('code') or match.groupdict().get('code2') or ''
                    if code:
                        return f'{prefix}{code}'
    except Exception as e:
        logger.error(f"Exception:{str(e)}")
        logger.error(traceback.format_exc())
    return None
