from support_site import SiteUtil
from ..setup import P

logger = P.logger


def has_show_data(show_data):
    return show_data not in (None, [], '')


def has_korean_last_episode(show_data):
    try:
        episode = show_data['seasons'][-1]['episodes'][-1]
        return SiteUtil.is_include_hangul(episode['title']) or SiteUtil.is_include_hangul(episode['summary'])
    except Exception as e:
        logger.debug(f"show_data validation failed: {str(e)}")
        return False
