import os
import re
import copy

import yaml

from ..setup import P
from .export_normalizer import TOP_LEVEL_KEY_ORDER, normalize_export_data, reorder_keys


class CleanDumper(yaml.SafeDumper):
    pass


class LiteralString(str):
    pass


def normalize_text(value):
    value = value.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    lines = [line.rstrip() for line in value.split('\n')]
    return '\n'.join(lines).strip()


def normalize_summary_text(value):
    value = normalize_text(value)
    lines = [line for line in value.split('\n') if line.strip()]
    return '\n'.join(lines).strip()


def sanitize_yaml_value(value, key=None):
    if isinstance(value, dict):
        return {child_key: sanitize_yaml_value(item, child_key) for child_key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_yaml_value(item, key) for item in value]
    if isinstance(value, str):
        if key == 'summary':
            return LiteralString(normalize_summary_text(value))
        if key == 'title':
            return LiteralString(normalize_text(value))
        return normalize_text(value)
    return value


def reorder_top_level_keys(show_data):
    if not isinstance(show_data, dict):
        return show_data
    return reorder_keys(show_data, TOP_LEVEL_KEY_ORDER)


def remove_episode_code_fields(show_data):
    if not isinstance(show_data, dict):
        return show_data
    cleaned = copy.deepcopy(show_data)
    seasons = cleaned.get('seasons')
    if not isinstance(seasons, list):
        return cleaned
    for season in seasons:
        if not isinstance(season, dict):
            continue
        episodes = season.get('episodes')
        if not isinstance(episodes, list):
            continue
        for episode in episodes:
            if isinstance(episode, dict):
                episode.pop('code', None)
    return cleaned


def represent_clean_string(dumper, value):
    style = '|' if '\n' in value else None
    return dumper.represent_scalar('tag:yaml.org,2002:str', value, style=style)


CleanDumper.add_representer(str, represent_clean_string)
CleanDumper.add_representer(LiteralString, lambda dumper, value: dumper.represent_scalar('tag:yaml.org,2002:str', value, style='|'))


def write_yaml(show_data, target_path=None):
    target_path = P.ModelSetting.get('manual_target')
    filename = re.sub('[\\/:*?"<>|]', '', show_data['title']).replace('  ', ' ').replace('[]', '').strip()
    clean_show_data = normalize_export_data(show_data)
    if not P.ModelSetting.get_bool('is_primary') and P.ModelSetting.get_bool('delete_title'):
        clean_show_data.pop('title', None)
    clean_show_data = sanitize_yaml_value(clean_show_data)
    # Normalize/serialize before opening the destination, so validation or dumper
    # errors do not truncate an existing YAML file. Storage policy is unchanged.
    output = yaml.dump(clean_show_data, Dumper=CleanDumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=4096)
    with open(os.path.join(target_path, filename + '.yaml'), 'w', encoding='utf-8') as outfile:
        outfile.write(output)
