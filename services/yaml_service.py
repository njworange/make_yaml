import os
import re

import yaml

from ..setup import P


class CleanDumper(yaml.SafeDumper):
    pass


def normalize_text(value):
    value = value.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    lines = [line.rstrip() for line in value.split('\n')]
    return '\n'.join(lines).strip()


def sanitize_yaml_value(value):
    if isinstance(value, dict):
        return {key: sanitize_yaml_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_yaml_value(item) for item in value]
    if isinstance(value, str):
        return normalize_text(value)
    return value


def represent_clean_string(dumper, value):
    style = '|' if '\n' in value else None
    return dumper.represent_scalar('tag:yaml.org,2002:str', value, style=style)


CleanDumper.add_representer(str, represent_clean_string)


def write_yaml(show_data, target_path=None):
    target_path = P.ModelSetting.get('manual_target')
    filename = re.sub('[\\/:*?"<>|]', '', show_data['title']).replace('  ', ' ').replace('[]', '').strip()
    with open(os.path.join(target_path, filename + '.yaml'), 'w', encoding='utf-8') as outfile:
        if not P.ModelSetting.get_bool('is_primary') and P.ModelSetting.get_bool('delete_title'):
            del show_data['title']
        clean_show_data = sanitize_yaml_value(show_data)
        yaml.dump(clean_show_data, outfile, Dumper=CleanDumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=4096)
