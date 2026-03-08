import copy
import traceback

from ..providers.legacy_registry import get_provider_class
from ..setup import P

logger = P.logger


def get_show_data(code):
    try:
        logger.debug(code)
        site = code[:2]
        site_code = code[2:]
        logger.debug(f"YAMLUTILS get_data parsed site={site} code={site_code}")
        provider_class = get_provider_class(site)
        show_data = provider_class.make_data(site_code)
        if isinstance(show_data, dict):
            logger.debug(f"YAMLUTILS get_data result site={site} type=dict keys={list(show_data.keys())} seasons={len(show_data.get('seasons', []))}")
        elif isinstance(show_data, list):
            logger.debug(f"YAMLUTILS get_data result site={site} type=list len={len(show_data)}")
        else:
            logger.debug(f"YAMLUTILS get_data result site={site} type={type(show_data).__name__} truthy={bool(show_data)}")
        if P.ModelSetting.get_int('split_season') != 1:
            season_data = []
            split_season = P.ModelSetting.get_int('split_season')
            for season in show_data['seasons']:
                index = int(season['index'])
                for split_index in range(split_season):
                    season_data.append({
                        'index': int(split_index * 100 + index),
                        'summary': copy.deepcopy(season.get('summary', '')),
                        'episodes': copy.deepcopy(season['episodes']),
                    })
            show_data['seasons'] = season_data
        return show_data
    except Exception as e:
        logger.error(f"Exception:{e} [site={site if 'site' in locals() else ''} code={site_code if 'site_code' in locals() else ''}]")
        logger.error(traceback.format_exc())
