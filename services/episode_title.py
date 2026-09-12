"""Shared display-date convention and removal of legacy display decoration."""

import re
from datetime import datetime


KOREAN_WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
_BROADCAST_PREFIX = re.compile(r'^\d{4}([.-])\d{1,2}\1\d{1,2}\([월화수목금토일]\)\s*')


def strip_broadcast_prefix(title):
    """Strip only the known leading date+Korean-weekday display syntax.

    This never supplies a date. Undecorated dates/numbers in real titles remain.
    Both padded and unpadded month/day prefixes are accepted, including repeated
    prefixes from older output, for idempotent export.
    """
    if title is None:
        return ''
    if not isinstance(title, str):
        raise ValueError('episode title must be a string')
    title = title.strip()
    while _BROADCAST_PREFIX.match(title):
        title = _BROADCAST_PREFIX.sub('', title, count=1).strip()
    return title


def format_korean_broadcast_date(date_text):
    """Existing provider convention; export passes a validated ISO date here."""
    if not date_text:
        return ''
    try:
        parsed = datetime.strptime(date_text[:10], '%Y-%m-%d')
        return f"{parsed.year:04d}.{parsed.month}.{parsed.day}({KOREAN_WEEKDAYS[parsed.weekday()]})"
    except ValueError:
        return ''


def format_episode_title(title, date_text):
    title = strip_broadcast_prefix(title)
    prefix = format_korean_broadcast_date(date_text)
    return f'{prefix} {title}' if prefix and title else prefix or title
