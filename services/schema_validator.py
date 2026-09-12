from support_site import SiteUtil
from ..setup import P
from .episode_title import strip_broadcast_prefix

logger = P.logger


def has_show_data(show_data):
    return show_data not in (None, [], '')


def has_korean_last_episode(show_data):
    try:
        episode = show_data['seasons'][-1]['episodes'][-1]
        # Legacy providers/cached output may already contain a Korean weekday.
        # Display decoration must not make English metadata pass this gate.
        title = strip_broadcast_prefix(episode.get('title'))
        summary = episode.get('summary') or ''
        return SiteUtil.is_include_hangul(title) or SiteUtil.is_include_hangul(summary)
    except Exception as e:
        logger.debug(f"show_data validation failed: {str(e)}")
        return False
