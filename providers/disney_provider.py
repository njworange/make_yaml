from .legacy_registry import get_provider_class


def get_legacy_disney_provider():
    return get_provider_class('FD')


def make_data(site_code):
    return get_legacy_disney_provider().make_data(site_code)
