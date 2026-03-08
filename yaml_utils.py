from .services.code_service import sort_code
from .services.provider_service import get_show_data
from .services.tmdb_service import apply_tmdb_data
from .services.yaml_service import write_yaml


class YAMLUTILS(object):

    @classmethod
    def make_yaml(cls, show_data, target_path=None):
        return write_yaml(show_data, target_path)

    @classmethod
    def code_sort(cls, user_order, url_list):
        return sort_code(user_order, url_list)

    @classmethod
    def get_data(cls, code):
        return get_show_data(code)

    @classmethod
    def tmdb_data(cls, tmdb_code, show_data):
        return apply_tmdb_data(tmdb_code, show_data)
