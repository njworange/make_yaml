import os
import re

import yaml

from ..setup import P


def write_yaml(show_data, target_path=None):
    target_path = P.ModelSetting.get('manual_target')
    filename = re.sub('[\\/:*?"<>|]', '', show_data['title']).replace('  ', ' ').replace('[]', '').strip()
    with open(os.path.join(target_path, filename + '.yaml'), 'w', encoding='utf-8') as outfile:
        if not P.ModelSetting.get_bool('is_primary') and P.ModelSetting.get_bool('delete_title'):
            del show_data['title']
        yaml.dump(show_data, outfile, sort_keys=False, allow_unicode=True)
