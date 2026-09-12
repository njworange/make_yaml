"""Synthetic offline fixtures; not live OTT, .pyf or FlaskFarm integration tests.

Run: python3 -B -m unittest discover -s tests -v
The writer is imported with a stub setup module. Provider functions are extracted
from the actual source AST to avoid loading opaque legacy modules or doing I/O.
"""

import ast
import copy
import html
import json
from datetime import date, datetime
import importlib.util
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = '_make_yaml_offline_fixture'
for name in (PACKAGE, PACKAGE + '.services'):
    module = ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module
setup = ModuleType(PACKAGE + '.setup')
setup.P = SimpleNamespace(logger=Mock())
sys.modules[setup.__name__] = setup


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


titles = load_module(PACKAGE + '.services.episode_title', ROOT / 'services/episode_title.py')
normalizer = load_module(PACKAGE + '.services.export_normalizer', ROOT / 'services/export_normalizer.py')
tving_dates = load_module(PACKAGE + '.services.tving_date_enrichment', ROOT / 'services/tving_date_enrichment.py')
writer = load_module(PACKAGE + '.services.yaml_service', ROOT / 'services/yaml_service.py')


def provider_namespace():
    names = {
        'get_show_data', 'normalize_tving_show_data', 'normalize_tving_episode_title',
        'format_korean_broadcast_date', 'extract_netflix_title_code',
        'extract_prime_detail_code', 'extract_ebs_program_id', 'extract_appletv_show_id',
        'decode_ebs_text', 'normalize_ebs_episode_title', 'enrich_ebs_episode',
        'normalize_prime_episode_title', 'normalize_prime_date', 'extract_prime_text',
        'extract_prime_episodes', 'enrich_appletv_episode', 'normalize_appletv_date',
        'normalize_wavve_show_data',
    }
    path = ROOT / 'services/provider_service.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    env = {
        'copy': copy, 're': re, 'html': html, 'datetime': datetime,
        'strip_broadcast_prefix': titles.strip_broadcast_prefix,
        'enrich_tving_dates': lambda code, value: value,
        'format_korean_broadcast_date': titles.format_korean_broadcast_date,
        'KOREAN_WEEKDAYS': list('월화수목금토일'), 'logger': Mock(),
        'traceback': SimpleNamespace(format_exc=lambda: 'stub traceback'),
        'P': SimpleNamespace(ModelSetting=SimpleNamespace(get_int=lambda key: 1)),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
    return env


def show_fixture():
    return {
        'extras': {'posters': 'extension data, not an image field'},
        'seasons': [{
            'summary': '시즌 설명',
            'episodes': [{
                'code': 'internal-episode-id', 'originally_available_at': '2025-05-10',
                'thumbs': 'https://example.invalid/episode.jpg', 'summary': '설명\n\n둘째 줄',
                'title': '2025.05.10(토) 회차 제목', 'index': 0,
            }],
            'title': '시즌 0', 'posters': ['https://example.invalid/season.jpg'], 'index': 0,
        }],
        'posters': [{'url': 'https://example.invalid/show.jpg', 'language': 'ko'}],
        'title': '작품 제목', 'code': 'KVP001767020', 'primary': False,
    }


class ExportBoundaryTests(unittest.TestCase):
    def test_order_extensions_and_numbering(self):
        result = normalizer.normalize_export_data(show_fixture())
        self.assertEqual(list(result)[:5], normalizer.TOP_LEVEL_KEY_ORDER)
        season = result['seasons'][0]
        self.assertEqual(list(season)[:4], normalizer.SEASON_KEY_ORDER)
        episode = season['episodes'][0]
        self.assertEqual(list(episode), normalizer.EPISODE_KEY_ORDER)
        self.assertEqual((season['index'], episode['index']), (0, 0))
        self.assertEqual(result['extras'], show_fixture()['extras'])
        self.assertEqual(season['summary'], '시즌 설명')
        self.assertEqual(episode['title'], '2025.5.10(토) 회차 제목')

    def test_deep_copy_and_idempotence(self):
        original = show_fixture()
        before = copy.deepcopy(original)
        result = normalizer.normalize_export_data(original)
        self.assertEqual(original, before)
        self.assertEqual(normalizer.normalize_export_data(result), result)
        result['posters'][0]['language'] = 'changed'
        self.assertEqual(original, before)

    def test_poster_shapes_and_empty_values(self):
        for value, expected in [
            ('u', [{'url': 'u'}]), (['u', 'v'], [{'url': 'u'}, {'url': 'v'}]),
            ({'url': 'u', 'language': 'ko'}, [{'url': 'u', 'language': 'ko'}]),
            ([None, '', {}, {'url': None}, {'url': ''}], []), (None, []), ('', []), ([], []),
        ]:
            with self.subTest(value=value):
                self.assertEqual(normalizer.normalize_posters(value), expected)

    def test_thumb_selection(self):
        for value, expected in [
            (' u ', 'u'), (['', None, {'url': 'u'}, 'v'], 'u'),
            ({'value': 'u', 'aspect': 'landscape'}, 'u'),
            ({'url': 'u', 'value': 'v'}, 'u'),
            (None, None), ('', None), ({}, None), ([], None), ({'url': None}, None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(normalizer.normalize_thumb(value), expected)

    def test_dates(self):
        for value in ['2024-02-29', '2024.02.29', date(2024, 2, 29), datetime(2024, 2, 29, 23),
                      '2024-02-29T23:59:00-03:00', '2024-02-29T23:59:00Z']:
            with self.subTest(value=value):
                self.assertEqual(normalizer.normalize_date(value), '2024-02-29')
        for value in [None, '', '  ']:
            self.assertIsNone(normalizer.normalize_date(value))
        for value in ['2025-02-29', '2025.02.29', '2026-99-99', '2025-5-10',
                      '2025.5.10', '05/10/2025', '2025.05.10(토)', 'https://x/20250510/', 20250510, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalizer.normalize_date(value)

    def test_missing_fields_not_invented(self):
        original = {'seasons': [{'index': 1, 'episodes': [{'index': 1, 'thumbs': '', 'originally_available_at': None}]}]}
        result = normalizer.normalize_export_data(original)
        self.assertNotIn('posters', result)
        self.assertNotIn('code', result)  # identity belongs to provider_service, not title guessing
        self.assertEqual(result['seasons'][0]['episodes'], [{'index': 1}])

    def test_unknown_nonempty_shapes_are_not_stringified(self):
        for field, value in [('posters', [123]), ('posters', [{'unknown': 'u'}]),
                             ('thumbs', {'unknown': 'u'}), ('thumbs', 42),
                             ('originally_available_at', 'not a date')]:
            original = {'title': '쇼', field: value}
            before = copy.deepcopy(original)
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalizer.normalize_export_data(original)
            self.assertEqual(original, before)

    def test_malformed_containers_fail(self):
        for value in [None, [], {'seasons': {}}, {'seasons': [None]},
                      {'seasons': [{'episodes': {}}]}, {'seasons': [{'episodes': [None]}]}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalizer.normalize_export_data(value)

    def test_writer_options_roundtrip_and_no_mutation(self):
        for is_primary in (False, True):
            for delete_title in (False, True):
                settings = SimpleNamespace(get=lambda key: '/configured', get_bool=lambda key: {
                    'is_primary': is_primary, 'delete_title': delete_title}[key])
                original = show_fixture()
                before = copy.deepcopy(original)
                opened = mock_open()
                with self.subTest(primary=is_primary, delete=delete_title), \
                        patch.object(writer, 'P', SimpleNamespace(ModelSetting=settings)), \
                        patch.object(writer, 'open', opened, create=True):
                    writer.write_yaml(original)
                text = opened().write.call_args.args[0]
                loaded = yaml.safe_load(text)
                self.assertEqual(original, before)
                self.assertEqual('title' in loaded, is_primary or not delete_title)
                self.assertIn('title: |-\n', text)  # season/episode titles remain literal
                self.assertIn('summary: |-\n', text)
                self.assertIn("originally_available_at: '2025-05-10'", text)
                self.assertIs(loaded['primary'], False)  # existing primary semantics preserved
                self.assertEqual(loaded['posters'], original['posters'])
                self.assertIsInstance(loaded['seasons'][0]['episodes'][0]['thumbs'], str)
                self.assertNotIn('code', loaded['seasons'][0]['episodes'][0])

    def test_invalid_export_fails_before_open(self):
        settings = SimpleNamespace(get=lambda key: '/configured', get_bool=lambda key: False)
        with patch.object(writer, 'P', SimpleNamespace(ModelSetting=settings)), \
                patch.object(writer, 'open', mock_open(), create=True) as opened:
            with self.assertRaises(ValueError):
                writer.write_yaml({'title': '쇼', 'posters': [123]})
        opened.assert_not_called()

    def test_tmdb_enrichment_is_normalized_at_export(self):
        tmdb = load_module(PACKAGE + '.services.tmdb_service', ROOT / 'services/tmdb_service.py')
        show_info = {
            'title': 'TMDB 제목', 'art': [{'aspect': 'poster', 'value': 'show-url'}],
            'studio': '', 'originaltitle': '', 'country': [], 'genre': [], 'mpaa': '',
            'premiered': '2025-05-10', 'ratings': [], 'actor': [], 'extra_info': {},
        }
        season_info = {
            'art': [{'aspect': 'poster', 'value': 'season-url'}], 'plot': '',
            'episodes': {0: {'premiered': '2025-05-10', 'art': [{'value': 'episode-url'}],
                             'writer': [], 'director': []}},
        }
        client = SimpleNamespace(info=lambda code: season_info if '_' in code else show_info,
                                 process_trans=lambda kind, value: value)
        metadata = ModuleType('metadata')
        metadata.__path__ = []
        ftv = ModuleType('metadata.mod_ftv')
        ftv.ModuleFtv = lambda name: client
        with patch.dict(sys.modules, {'metadata': metadata, 'metadata.mod_ftv': ftv}):
            enriched = tmdb.apply_tmdb_data('FT1', show_fixture())
        before = copy.deepcopy(enriched)
        result = normalizer.normalize_export_data(enriched)
        self.assertEqual(result['posters'], [{'url': 'show-url'}])
        self.assertEqual(result['seasons'][0]['posters'], [{'url': 'season-url'}])
        self.assertEqual(result['seasons'][0]['episodes'][0]['thumbs'], 'episode-url')
        self.assertEqual(enriched, before)


class ProviderBoundaryTests(unittest.TestCase):
    def test_provider_title_decoration_moves_to_export(self):
        env = provider_namespace()
        episode = {'index': 1, 'title': '2020.01.01(수) English title',
                   'summary': '설명', 'originally_available_at': '2025-05-10'}
        env['fetch_wavve_episode_metadata'] = lambda *args: {'by_index': {}, 'by_title': {}}
        wavve = env['normalize_wavve_show_data']('id', {'seasons': [{'episodes': [copy.deepcopy(episode)]}]})
        ebs = env['enrich_ebs_episode'](copy.deepcopy(episode))
        prime = env['extract_prime_episodes'](
            '<div>시즌 1 에피소드 1 - English title</div>'
            '<div>2025년 5월 10일</div><div>40분</div><div>설명</div>'
        )['episodes'][0]
        for value in (wavve['seasons'][0]['episodes'][0], ebs, prime):
            self.assertEqual(value['title'], 'English title')
            exported = normalizer.normalize_export_data({'seasons': [{'episodes': [value]}]})
            self.assertEqual(exported['seasons'][0]['episodes'][0]['title'], '2025.5.10(토) English title')

    def test_apple_title_without_detail_or_on_detail_failure(self):
        env = provider_namespace()
        env['fetch_appletv_html'] = Mock(side_effect=RuntimeError('offline'))
        for url in ('', 'https://example.invalid/episode'):
            result = env['enrich_appletv_episode']({
                'title': '2020.01.01(수) Title', 'originally_available_at': '2025-05-10', 'url': url,
            })
            self.assertEqual(result['title'], 'Title')
            exported = normalizer.normalize_export_data({'seasons': [{'episodes': [result]}]})
            self.assertEqual(exported['seasons'][0]['episodes'][0]['title'], '2025.5.10(토) Title')

    def test_tving_never_uses_thumbnail_date(self):
        env = provider_namespace()
        for value in [None, '', '   ']:
            for thumb in ['https://example.invalid/20260912/a.jpg', 'https://example.invalid/20269999/a.jpg', '']:
                episode = {'index': 1, 'title': '1. 실제 제목', 'thumbs': thumb, 'originally_available_at': value}
                original = {'seasons': [{'index': 1, 'episodes': [episode]}]}
                before = copy.deepcopy(original)
                result = env['normalize_tving_show_data'](original)
                self.assertEqual(original, before)
                self.assertEqual(result['seasons'][0]['episodes'][0]['title'], '실제 제목')
                exported = normalizer.normalize_export_data(result)['seasons'][0]['episodes'][0]
                self.assertNotIn('originally_available_at', exported)

    def test_tving_preserves_real_date_and_no_date_key(self):
        env = provider_namespace()
        for date_fields, expected in [({}, '실제 제목'), ({'originally_available_at': '2020-01-01'}, '2020.1.1(수) 실제 제목')]:
            original = {'seasons': [{'episodes': [{'title': '1. 실제 제목', 'thumbs': 'https://x/20260912/a', **date_fields}]}]}
            result = env['normalize_tving_show_data'](original)['seasons'][0]['episodes'][0]
            self.assertEqual(result['title'], '실제 제목')  # decoration now belongs to export
            self.assertEqual(result.get('originally_available_at'), date_fields.get('originally_available_at'))
            exported = normalizer.normalize_export_data({'seasons': [{'episodes': [result]}]})
            self.assertEqual(exported['seasons'][0]['episodes'][0]['title'], expected)

    def test_canonical_ids_and_input_ownership(self):
        cases = [
            ('FNhttps://www.netflix.com/title/81519223', None, 'FN81519223', 'build_netflix_show_data'),
            ('FPhttps://www.primevideo.com/detail/0N3EDITHIBCK6E9G5PPZZQYOGQ', None, 'FP0N3EDITHIBCK6E9G5PPZZQYOGQ', 'build_prime_show_data'),
            ('KEhttps://anikids.ebs.co.kr/anikids/program/show/10024440', None, 'KE10024440', 'build_ebs_show_data'),
            ('FAumc.cmc.example', 'umc.cmc.example', 'FAumc.cmc.example', 'build_appletv_show_data'),
            ('FAumc.cmc.example', 'FAumc.cmc.example', 'FAumc.cmc.example', 'build_appletv_show_data'),
            ('FAumc.cmc.example', None, 'FAumc.cmc.example', 'build_appletv_show_data'),
            ('FN81519223', 'FNexisting', 'FNexisting', 'build_netflix_show_data'),
        ]
        for code, existing, expected, builder in cases:
            env = provider_namespace()
            original = {'title': '쇼', 'seasons': []}
            if existing is not None:
                original['code'] = existing
            before = copy.deepcopy(original)
            env[builder] = Mock(return_value=original)
            legacy = Mock()
            env['get_provider_class'] = lambda site: legacy
            result = env['get_show_data'](code)
            with self.subTest(code=code, existing=existing):
                self.assertEqual(result['code'], expected)
                self.assertEqual(original, before)
                legacy.make_data.assert_not_called()

    def test_existing_fallback_policy(self):
        for prefix, builder in [('FN', 'build_netflix_show_data'), ('FP', 'build_prime_show_data'),
                                ('KE', 'build_ebs_show_data'), ('FA', 'build_appletv_show_data')]:
            for empty in (None, '', []):
                with self.subTest(prefix=prefix, empty=empty):
                    env = provider_namespace()
                    events = []
                    def public(code):
                        events.append('public')
                        return empty
                    def legacy_result(code):
                        events.append('legacy')
                        return {'title': '레거시 쇼', 'seasons': []}
                    env[builder] = public
                    env['get_provider_class'] = lambda site: SimpleNamespace(make_data=legacy_result)
                    result = env['get_show_data'](prefix + '12345678')
                    self.assertEqual(events, ['public'] if prefix == 'FA' else ['public', 'legacy'])
                    if prefix == 'FA':
                        self.assertEqual(result, empty)
                    else:
                        self.assertEqual(result['code'], prefix + '12345678')

    def test_unrelated_legacy_identity_and_split_mapping(self):
        for site in ['KW', 'KV', 'FD', 'KC']:
            env = provider_namespace()
            env['P'].ModelSetting.get_int = lambda key: 2
            original = {'code': 'existing-code', 'seasons': [{'index': 1, 'episodes': [{'index': 7, 'title': '회차'}]}]}
            env['get_provider_class'] = lambda prefix: SimpleNamespace(make_data=lambda code: original)
            env['normalize_wavve_show_data'] = lambda code, value: value
            result = env['get_show_data'](site + 'id')
            self.assertEqual(result['code'], 'existing-code')
            self.assertEqual([season['index'] for season in result['seasons']], [1, 101])
            self.assertEqual([season['episodes'][0]['index'] for season in result['seasons']], [7, 7])


class EpisodeTitleAndErrorTests(unittest.TestCase):
    def test_unpadded_display_keeps_iso_date_field(self):
        for day, display in [
            ('2026-02-10', '2026.2.10(화)'),  # month only
            ('2026-10-02', '2026.10.2(금)'),  # day only
            ('2026-02-03', '2026.2.3(화)'),   # both single-digit
            ('2026-10-12', '2026.10.12(월)'), # both double-digit
            ('2024-02-29', '2024.2.29(목)'),  # leap day
            ('0001-01-01', '0001.1.1(월)'),   # four-digit year, independent of strftime padding
        ]:
            for title in ('제목', '', None):
                with self.subTest(day=day, title=title):
                    original = {'seasons': [{'episodes': [{'title': title, 'originally_available_at': day}]}]}
                    before = copy.deepcopy(original)
                    result = normalizer.normalize_export_data(original)
                    episode = result['seasons'][0]['episodes'][0]
                    self.assertEqual(episode['title'], display + (' 제목' if title else ''))
                    self.assertEqual(episode['originally_available_at'], day)
                    self.assertEqual(normalizer.normalize_export_data(result), result)
                    self.assertEqual(original, before)
                    loaded = yaml.safe_load(yaml.dump(writer.sanitize_yaml_value(result), Dumper=writer.CleanDumper))
                    self.assertEqual(loaded['seasons'][0]['episodes'][0]['originally_available_at'], day)

    def test_padded_unpadded_prefixes_in_shared_provider_paths(self):
        env = provider_namespace()
        env['fetch_wavve_episode_metadata'] = lambda *args: {'by_index': {}, 'by_title': {}}
        for prefix in [
            '2026.02.03(화)', '2026.2.03(화)', '2026.02.3(화)', '2026.2.3(화)',
            '2026-02-03(화)', '2026-2-03(화)', '2026-02-3(화)', '2026-2-3(화)',
            '2025.05.10(토) 2026.2.3(화) 2026-02-03(화)',
        ]:
            with self.subTest(prefix=prefix):
                title = prefix + ' English title'
                self.assertEqual(titles.strip_broadcast_prefix(title), 'English title')
                for day, expected in [(None, 'English title'), ('2026-02-10', '2026.2.10(화) English title')]:
                    self.assertEqual(titles.format_episode_title(title, day), expected)
                self.assertEqual(env['normalize_ebs_episode_title']('1. ' + title), 'English title')
                self.assertEqual(env['normalize_ebs_episode_title'](title), 'English title')
                self.assertEqual(env['normalize_prime_episode_title']('시즌 1 에피소드 1 - ' + title), 'English title')
                self.assertEqual(env['enrich_appletv_episode']({'title': title})['title'], 'English title')
                self.assertEqual(env['normalize_tving_episode_title'](title), 'English title')
                self.assertEqual(env['normalize_tving_episode_title']('1. ' + title), 'English title')
                data = {'seasons': [{'episodes': [{'index': 1, 'title': title}]}]}
                wavve = env['normalize_wavve_show_data']('id', data)
                self.assertEqual(wavve['seasons'][0]['episodes'][0]['title'], 'English title')

    def test_prefix_matching_stays_narrow(self):
        for title in ['2026.2.10 특집', '2026.02.10 특집', '2026-2-10 특집',
                      '제목 2026.2.10(화)', '2026.2-10(화) 제목', '2026.222.10(화) 제목',
                      '2026.2.10(Tue) Title']:
            with self.subTest(title=title):
                self.assertEqual(titles.strip_broadcast_prefix(title), title)
                self.assertEqual(titles.format_episode_title(title, None), title)

    def test_title_date_matrix_and_idempotence(self):
        cases = [
            ('제목', '2025-05-10', '2025.5.10(토) 제목'),
            ('', '2025-05-10', '2025.5.10(토)'),
            (None, '2025.05.10', '2025.5.10(토)'),
            ('제목', None, '제목'), ('', None, ''),
            ('2020.01.01(수) Title', None, 'Title'),
            ('2020-01-01(수) Title', '2025-05-10', '2025.5.10(토) Title'),
            ('2020.01.01(수) 2021.01.01(금) Title', '2025-05-10', '2025.5.10(토) Title'),
            ('2025.05.10 특집', None, '2025.05.10 특집'),
            ('1. Original title', None, '1. Original title'),
        ]
        for title, day, expected in cases:
            with self.subTest(title=title, day=day):
                original = {'seasons': [{'episodes': [{'title': title, 'originally_available_at': day}]}]}
                before = copy.deepcopy(original)
                result = normalizer.normalize_export_data(original)
                self.assertEqual(result['seasons'][0]['episodes'][0]['title'], expected)
                self.assertEqual(original, before)
                self.assertEqual(normalizer.normalize_export_data(result), result)
        result = normalizer.normalize_export_data({'seasons': [{'episodes': [{'originally_available_at': '2025-05-10'}]}]})
        self.assertEqual(result['seasons'][0]['episodes'][0]['title'], '2025.5.10(토)')

    def test_all_provider_prefixes_share_the_export_rule(self):
        for prefix in ('KW', 'KV', 'FN', 'FD', 'FP', 'FA', 'KE', 'KC'):
            value = show_fixture()
            value['code'] = prefix + 'fixture'
            value['seasons'][0]['episodes'][0]['title'] = 'Title'
            result = normalizer.normalize_export_data(value)
            self.assertEqual(result['seasons'][0]['episodes'][0]['title'], '2025.5.10(토) Title')

    def test_final_title_uses_date_after_enrichment(self):
        value = show_fixture()
        episode = value['seasons'][0]['episodes'][0]
        episode['originally_available_at'] = '2024-02-29'
        result = normalizer.normalize_export_data(value)
        self.assertEqual(result['seasons'][0]['episodes'][0]['title'], '2024.2.29(목) 회차 제목')
        episode['originally_available_at'] = ''
        result = normalizer.normalize_export_data(value)
        self.assertEqual(result['seasons'][0]['episodes'][0]['title'], '회차 제목')

    def test_korean_gate_ignores_display_weekdays(self):
        support = ModuleType('support_site')
        support.SiteUtil = SimpleNamespace(is_include_hangul=lambda text: bool(re.search('[가-힣]', text)))
        with patch.dict(sys.modules, {'support_site': support}):
            validator = load_module(PACKAGE + '.services.schema_validator', ROOT / 'services/schema_validator.py')
        for title, summary, expected in [
            ('2025.05.10(토) English title', 'English summary', False),
            ('2025.05.10(토)', '', False),
            ('2025-05-10(토) 2024.01.01(월) Title', '', False),
            ('2026.2.10(화) English title', 'English summary', False),
            ('2026.2.3(화)', '', False),
            ('2025.05.10(토) 2026-2-3(화) Title', '', False),
            ('2026.2.10(화) 한글 제목', '', True),
            ('한글 제목', '', True), (None, '한국어 요약', True), ('', 'English', False),
        ]:
            data = {'seasons': [{'episodes': [{'title': title, 'summary': summary}]}]}
            self.assertEqual(validator.has_korean_last_episode(data), expected)
        self.assertFalse(validator.has_korean_last_episode({'seasons': []}))

    def test_command_handles_validation_and_successful_export(self):
        path = ROOT / 'mod_main.py'
        cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef))
        command = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process_command')
        settings = SimpleNamespace(get=lambda key: '/configured', get_bool=lambda key: False)
        for field, bad_value, success in [('posters', [123], False),
                                          ('originally_available_at', '2025-02-29', False),
                                          ('title', '', True)]:
            data = show_fixture()
            data['seasons'][0]['episodes'][0][field] = bad_value
            env = {
                'jsonify': lambda payload: payload, 'logger': Mock(),
                'P': SimpleNamespace(ModelSetting=settings),
                'is_command_enabled': lambda command: True,
                'build_direct_code': lambda command, code: 'KV' + code,
                'has_show_data': lambda value: True,
                'has_korean_last_episode': lambda value: True,
                'get_site_name': lambda site: '티빙',
                'YAMLUTILS': SimpleNamespace(get_data=lambda code: data, make_yaml=writer.write_yaml),
            }
            exec(compile(ast.Module(body=[command], type_ignores=[]), str(path), 'exec'), env)
            with patch.object(writer, 'P', env['P']), patch.object(writer, 'open', mock_open(), create=True) as opened:
                response = env['process_command'](SimpleNamespace(), 'tving_code', 'id', '', '', None)
            if success:
                self.assertEqual(response['ret'], 'success')
                exported = yaml.safe_load(opened().write.call_args.args[0])
                self.assertEqual(exported['seasons'][0]['episodes'][0]['title'], '2025.5.10(토)')
                env['logger'].error.assert_not_called()
            else:
                self.assertEqual(response['ret'], 'fail')
                self.assertIn('YAML 데이터 형식 오류', response['msg'])
                opened.assert_not_called()
                env['logger'].error.assert_called_once()


class TvingDateEnrichmentTests(unittest.TestCase):
    @staticmethod
    def show(episodes=None, season=1):
        return {'code': 'KVP001', 'title': '작품', 'seasons': [
            {'index': season, 'title': '시즌 제목', 'episodes': episodes if episodes is not None else [
                {'index': 1, 'title': '한국어 회차', 'summary': '원본 요약'}]}]}

    @staticmethod
    def row(code='E001', frequency=1, day='20240229'):
        return {'episode': {'code': code, 'frequency': frequency, 'broadcast_date': day,
                            'synopsis': {'ko': '덮어쓰면 안 되는 요약'}, 'image': []}}

    def run_enrich(self, show, pages=None, client=None):
        if client is None:
            client = SimpleNamespace(
                get_program_programid=Mock(return_value={'code': 'P001', 'broad_dt': '19990101'}),
                get_frequency_programid=Mock(side_effect=pages if pages is not None else [
                    {'result': [self.row()], 'has_more': 'N'}]))
        self.client = client
        support = ModuleType('support_site')
        support.SupportTving = client
        before = copy.deepcopy(show)
        with patch.dict(sys.modules, {'support_site': support}):
            result = tving_dates.enrich_tving_dates('P001', show)
        self.assertEqual(show, before)
        return result

    def test_code_priority_and_single_season_frequency_export(self):
        original = self.show([{'index': 1, 'title': '원본 제목'},
                              {'code': 'KVE002', 'index': 99, 'title': '2. 다른 제목'}])
        result = self.run_enrich(original, [{'result': [self.row(), self.row('E002', 2, 20260301)],
                                             'has_more': 'N'}])
        episodes = result['seasons'][0]['episodes']
        self.assertEqual([e['originally_available_at'] for e in episodes], ['2024-02-29', '2026-03-01'])
        self.assertEqual([e['title'] for e in episodes], ['원본 제목', '2. 다른 제목'])
        self.assertIsNot(result, original)
        exported = normalizer.normalize_export_data(result)
        self.assertEqual(exported['seasons'][0]['episodes'][0]['title'], '2024.2.29(목) 원본 제목')
        self.assertNotIn('code', exported['seasons'][0]['episodes'][1])
        self.client.get_program_programid.assert_called_once_with('P001')
        self.client.get_frequency_programid.assert_called_once_with('P001', page=1)
        self.assertEqual(self.run_enrich(result), result)
        self.client.get_program_programid.assert_not_called()

    def test_existing_dates_and_all_other_fields_are_preserved(self):
        for existing in ['2020-01-01', '2020.01.01', '2020-01-01T23:00:00Z',
                         date(2020, 1, 1), 'not-a-date', [], False]:
            show = self.show([{'index': 1, 'title': '제목', 'originally_available_at': existing}])
            with self.subTest(existing=existing):
                self.assertEqual(self.run_enrich(show), show)
                self.client.get_program_programid.assert_not_called()
        for empty in [None, '', '   ']:
            show = self.show()
            show['seasons'][0]['episodes'][0]['originally_available_at'] = empty
            result = self.run_enrich(show)
            expected = copy.deepcopy(show)
            expected['seasons'][0]['episodes'][0]['originally_available_at'] = '2024-02-29'
            self.assertEqual(result, expected)

    def test_invalid_or_missing_broadcast_dates_never_use_other_dates(self):
        for day in [None, '', '20230229', '20241301', '20240010', 0, True, {}, [],
                    '2024.2.29', '1709164800', 'https://image/20240229/a', '20240229120000']:
            with self.subTest(day=day):
                show = self.show()
                show['seasons'][0]['episodes'][0]['thumbs'] = 'https://image/20240229/a'
                self.assertEqual(self.run_enrich(show, [{'result': [self.row(day=day)], 'has_more': 'N'}]), show)
        row = self.row()
        del row['episode']['broadcast_date']
        self.assertEqual(self.run_enrich(self.show(), [{'result': [row], 'has_more': 'N'}]), self.show())

    def test_remote_date_formats_use_existing_export_validator(self):
        for day in ['20240229', 20240229, '2024-02-29', '2024.02.29', '2024-02-29T23:00:00+09:00']:
            result = self.run_enrich(self.show(), [{'result': [self.row(day=day)], 'has_more': 'N'}])
            self.assertEqual(result['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')

    def test_supplied_code_never_falls_back_and_accepts_raw_or_prefixed(self):
        for code in ['E404', 'KVE404', 1, [], '   ']:
            show = self.show([{'index': 1, 'code': code, 'title': '제목'}])
            self.assertEqual(self.run_enrich(show), show)
        for code in ['E001', 'KVE001']:
            show = self.show([{'index': 999, 'code': code, 'title': '제목'}], season=4)
            self.assertEqual(self.run_enrich(show)['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')

    def test_frequency_scope_requires_unique_program_bound_season_one(self):
        shows = [self.show(season=value) for value in [0, 2, None, True, 1.0, 'season 1']]
        missing_code = self.show()
        del missing_code['code']
        shows.append(missing_code)
        multi = self.show()
        multi['seasons'].append({'index': 2, 'episodes': [{'index': 1, 'title': '시즌2'}]})
        shows.append(multi)
        for show in shows:
            with self.subTest(show=show):
                self.assertEqual(self.run_enrich(show), show)
        show = self.show([{'index': '01', 'title': '제목'}], season='1')
        result = self.run_enrich(show, [{'result': [self.row(frequency='01')], 'has_more': 'N'}])
        self.assertEqual(result['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')
        for value in [0, -1, True, 1.0, '1-2', '1회', None]:
            self.assertEqual(self.run_enrich(self.show(), [{'result': [self.row(frequency=value)], 'has_more': 'N'}]), self.show())

    def test_codes_can_match_across_seasons_without_frequency_inference(self):
        show = self.show([{'index': 1, 'code': 'KVE001', 'title': '시즌1'}])
        show['seasons'].append({'index': 2, 'episodes': [{'index': 1, 'code': 'E002', 'title': '시즌2'}]})
        result = self.run_enrich(show, [{'result': [self.row(), self.row('E002', 1, '20260301')], 'has_more': 'N'}])
        self.assertEqual([s['episodes'][0]['originally_available_at'] for s in result['seasons']],
                         ['2024-02-29', '2026-03-01'])

    def test_duplicate_source_keys_are_ambiguous_even_with_invalid_dates(self):
        for episodes, rows in [
            ([{'index': 1}], [self.row(), self.row('E002', 1)]),
            ([{'index': 1, 'code': 'E001'}], [self.row(), self.row('E001', 2)]),
            ([{'index': 1}], [self.row(), self.row('E001', 2)]),
            ([{'index': 1}], [self.row(), self.row('E002', 1, 'bad')]),
        ]:
            show = self.show(episodes)
            self.assertEqual(self.run_enrich(show, [{'result': rows, 'has_more': 'N'}]), show)

    def test_duplicate_targets_and_mixed_code_frequency_claims_are_ambiguous(self):
        for episodes in [
            [{'index': 1}, {'index': 1}],
            [{'index': 1}, {'index': 2, 'code': 'E001'}],
            [{'index': 1}, {'index': 2, 'code': 'E001', 'originally_available_at': '2020-01-01'}],
            [{'index': 1}, {'index': 1, 'code': 'E404'}],
            [{'code': 'E001'}, {'code': 'KVE001'}],
        ]:
            show = self.show(episodes)
            self.assertEqual(self.run_enrich(show), show)

    def test_complete_pagination_and_late_duplicate_detection(self):
        show = self.show([{'index': 1}, {'index': 2}])
        pages = [{'result': [self.row()], 'has_more': 'Y'},
                 {'result': [self.row('E002', 2, '20260301')], 'has_more': 'N'}]
        result = self.run_enrich(show, pages)
        self.assertEqual([e['originally_available_at'] for e in result['seasons'][0]['episodes']],
                         ['2024-02-29', '2026-03-01'])
        self.assertEqual([c.kwargs['page'] for c in self.client.get_frequency_programid.call_args_list], [1, 2])
        pages[1] = {'result': [self.row('E002', 1)], 'has_more': 'N'}
        self.assertEqual(self.run_enrich(show, pages), show)

    def test_partial_empty_repeated_and_capped_pages_discard_all_updates(self):
        first = {'result': [self.row()], 'has_more': 'Y'}
        for tail in [RuntimeError('synthetic failure'), {'result': [], 'has_more': 'Y'},
                     first, {'result': [self.row()], 'has_more': 'N'}, {}, None]:
            with self.subTest(tail=tail):
                self.assertEqual(self.run_enrich(self.show(), [first, tail]), self.show())
                self.assertEqual(self.client.get_frequency_programid.call_count, 2)
        pages = [{'result': [self.row(f'E{i:03}', i)], 'has_more': 'Y'}
                 for i in range(1, tving_dates.MAX_PAGES + 1)]
        self.assertEqual(self.run_enrich(self.show(), pages), self.show())
        self.assertEqual(self.client.get_frequency_programid.call_count, tving_dates.MAX_PAGES)
        pages[-1]['has_more'] = 'N'
        self.assertIn('originally_available_at', self.run_enrich(self.show(), pages)['seasons'][0]['episodes'][0])
        result = self.run_enrich(self.show(), [first, {'result': [], 'has_more': 'N'}])
        self.assertEqual(result['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')

    def test_malformed_payload_and_program_identity_fail_closed(self):
        for payload in [None, [], '', {}, {'result': []}, {'result': [], 'has_more': True},
                        {'result': {}, 'has_more': 'N'}, {'result': [None], 'has_more': 'N'},
                        {'result': [{'episode': []}], 'has_more': 'N'},
                        {'result': [{}], 'has_more': 'N'}, {'result': [], 'has_more': 'N'}]:
            self.assertEqual(self.run_enrich(self.show(), [payload]), self.show())
        for program in [None, {}, {'code': 'P002'}, {'code': '0000'}, {'code': 1}]:
            client = SimpleNamespace(get_program_programid=Mock(return_value=program),
                                     get_frequency_programid=Mock())
            self.assertEqual(self.run_enrich(self.show(), client=client), self.show())
            client.get_frequency_programid.assert_not_called()
        show = self.show()
        show['code'] = 'KVP002'
        self.assertEqual(self.run_enrich(show), show)
        self.client.get_program_programid.assert_not_called()

    def test_missing_plugin_methods_and_api_errors_are_safe(self):
        show = self.show()
        with patch.object(tving_dates.importlib, 'import_module', side_effect=ImportError('missing')):
            self.assertEqual(tving_dates.enrich_tving_dates('P001', show), show)
        with patch.dict(sys.modules, {'support_site': ModuleType('support_site')}):
            self.assertEqual(tving_dates.enrich_tving_dates('P001', show), show)
        for client in [SimpleNamespace(),
                       SimpleNamespace(get_program_programid=Mock(side_effect=RuntimeError('auth/network failure'))),
                       SimpleNamespace(get_program_programid=Mock(return_value={'code': 'P001'}))]:
            self.assertEqual(self.run_enrich(show, client=client), show)

    def test_invalid_local_data_does_not_trigger_optional_io(self):
        for show in [None, [], '', {}, {'seasons': {}}, {'seasons': [None]},
                     {'seasons': [{'index': 1, 'episodes': {}}]},
                     {'seasons': [{'index': 1, 'episodes': [None]}]}]:
            self.assertEqual(self.run_enrich(show), show)
            self.client.get_program_programid.assert_not_called()

    def test_provider_boundary_failure_success_and_split_order(self):
        for fail in (False, True):
            show = self.show([{'index': 1, 'code': 'KVE001', 'title': '1. 한국어 제목'}])
            before = copy.deepcopy(show)
            env = provider_namespace()
            env['enrich_tving_dates'] = tving_dates.enrich_tving_dates
            env['get_provider_class'] = lambda site: SimpleNamespace(make_data=lambda code: show)
            env['P'].ModelSetting.get_int = lambda key: 2
            client = SimpleNamespace(
                get_program_programid=Mock(return_value={'code': 'P001'}),
                get_frequency_programid=Mock(side_effect=RuntimeError('failure') if fail else None,
                    return_value={'result': [self.row()], 'has_more': 'N'}))
            support = ModuleType('support_site')
            support.SupportTving = client
            with patch.dict(sys.modules, {'support_site': support}):
                result = env['get_show_data']('KVP001')
            self.assertEqual(show, before)
            self.assertEqual([s['index'] for s in result['seasons']], [1, 101])
            for season in result['seasons']:
                self.assertEqual(season['episodes'][0]['title'], '한국어 제목')
                self.assertEqual('originally_available_at' in season['episodes'][0], not fail)
            normalizer.normalize_export_data(result)  # both paths remain valid export input
            client.get_frequency_programid.assert_called_once()


class TvingDiagnosticTests(unittest.TestCase):
    show = staticmethod(TvingDateEnrichmentTests.show)
    row = staticmethod(TvingDateEnrichmentTests.row)

    def setUp(self):
        self.logger = Mock()
        self.log_patch = patch.object(setup.P, 'logger', self.logger)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def diagnose(self, show=None, pages=None, client=None):
        self.logger.reset_mock()
        result = TvingDateEnrichmentTests.run_enrich(
            self, self.show() if show is None else show, pages, client)
        self.logger.info.assert_called_once()
        text = self.logger.info.call_args.args[0]
        self.assertTrue(text.startswith('TVING_DATE_DIAG '))
        self.logger.error.assert_not_called()
        return result, json.loads(text.split(' ', 1)[1])

    def test_applied_summary_is_log_only(self):
        result, log = self.diagnose()
        self.assertEqual(log['reason'], 'APPLIED')
        self.assertEqual(log['applied'], 1)
        self.assertTrue(log['program_match'])
        self.assertTrue(log['local_program_match'])
        self.assertEqual(log['frequency_attempts'], 1)
        self.assertEqual(log['code_attempts'], 0)
        self.assertEqual(log['source_date_valid'], 1)
        self.assertEqual(log['unique_candidates'], 1)
        self.assertEqual(log['pages'], [{'page': 1, 'rows': 1, 'has_more': 'N'}])
        expected = self.show()
        expected['seasons'][0]['episodes'][0]['originally_available_at'] = '2024-02-29'
        self.assertEqual(result, expected)
        exported = yaml.safe_dump(normalizer.normalize_export_data(result), allow_unicode=True)
        for field in ['TVING_DATE_DIAG', 'reason_counts', 'matching_started', 'program_match']:
            self.assertNotIn(field, exported)

    def test_page_cap_and_scope_diagnosed_together_before_matching(self):
        show = self.show()
        del show['seasons'][0]['index']
        pages = [{'result': [self.row(f'E{i}', i)], 'has_more': 'Y'} for i in range(1, 11)]
        result, log = self.diagnose(show, pages)
        self.assertEqual(result, show)
        self.assertEqual(log['reason'], 'PAGE_CAP_REACHED_DISCARD')
        self.assertEqual(log['page'], 10)
        self.assertEqual(len(log['pages']), 10)
        self.assertEqual(log['source_date_valid'], 10)
        self.assertEqual(log['scope_reason'], 'NO_SEASON1_SCOPE')
        self.assertEqual(log['seasons'][0]['index_state'], 'MISSING')
        self.assertFalse(log['matching_started'])
        self.assertEqual(log['frequency_attempts'], 0)
        self.assertEqual(log['applied'], 0)

    def test_season_reasons_are_not_code_match_prohibitions(self):
        show = self.show(season=2)
        _, log = self.diagnose(show)
        self.assertEqual(log['reason_counts']['NO_SEASON1_SCOPE'], 1)
        show['seasons'].append({'index': 3, 'episodes': [{'index': 1}]})
        _, log = self.diagnose(show)
        self.assertEqual(log['reason_counts']['MULTI_SEASON_SKIPPED'], 2)
        self.assertEqual(log['season_count'], 2)
        show['seasons'][0]['episodes'][0]['code'] = 'E001'
        _, log = self.diagnose(show)
        self.assertEqual(log['reason'], 'APPLIED')
        self.assertEqual(log['code_attempts'], 1)
        self.assertEqual(log['reason_counts']['MULTI_SEASON_SKIPPED'], 1)

    def test_matching_and_date_reasons(self):
        for show, rows, expected in [
            (self.show([{'index': 1, 'code': 'E404'}]), [self.row()], 'CODE_MISMATCH'),
            (self.show([{'index': 9}]), [self.row()], 'NO_CANDIDATE'),
            (self.show(), [self.row(day='bad')], 'DATE_INVALID'),
            (self.show(), [self.row(day=None)], 'DATE_MISSING'),
            (self.show(), [self.row(), self.row('E002', 1)], 'AMBIGUOUS_FREQUENCY'),
            (self.show([{'code': 'E001'}]), [self.row(), self.row('E001', 2)], 'AMBIGUOUS_CODE'),
            (self.show(), [self.row(), self.row('E001', 2)], 'AMBIGUOUS_SOURCE_CODE'),
            (self.show([{'index': 1}, {'index': 1}]), [self.row()], 'DUPLICATE_TARGET'),
            (self.show([{'index': 1}, {'code': 'E001', 'index': 2}]), [self.row()], 'SOURCE_REUSED'),
        ]:
            with self.subTest(expected=expected):
                result, log = self.diagnose(show, [{'result': rows, 'has_more': 'N'}])
                self.assertEqual(result, show)
                self.assertEqual(log['reason'], 'NO_UPDATES')
                self.assertGreater(log['reason_counts'][expected], 0)
                if expected in ('DATE_INVALID', 'DATE_MISSING'):
                    self.assertEqual(log['reason_counts']['MATCHED_DATE_UNAVAILABLE'], 1)

    def test_fetch_and_local_exit_reasons(self):
        for payload, expected in [
            (None, 'PAGE_RESPONSE_INVALID'), ({'result': {} , 'has_more': 'N'}, 'PAGE_RESULT_INVALID'),
            ({'result': [{}], 'has_more': 'N'}, 'PAGE_EPISODE_INVALID'),
            ({'result': [], 'has_more': 'Y'}, 'EMPTY_PAGE_DISCARD'),
            ({'result': [], 'has_more': 'N'}, 'NO_SOURCE_ROWS'),
        ]:
            _, log = self.diagnose(pages=[payload])
            self.assertEqual(log['reason'], expected)
        page = {'result': [self.row()], 'has_more': 'Y'}
        _, log = self.diagnose(pages=[page, page])
        self.assertEqual(log['reason'], 'REPEATED_PAGE_DISCARD')
        self.assertEqual(log['page'], 2)
        for program, expected in [(None, 'PROGRAM_RESPONSE_INVALID'), ({'code': 'P404'}, 'NO_PROGRAM_MATCH')]:
            _, log = self.diagnose(client=SimpleNamespace(get_program_programid=Mock(return_value=program)))
            self.assertEqual(log['reason'], expected)
        show = self.show()
        show['code'] = 'P404'
        _, log = self.diagnose(show)
        self.assertEqual(log['reason'], 'LOCAL_PROGRAM_MISMATCH')
        self.assertIsNone(log['program_match'])
        show = self.show([{'originally_available_at': '2024-02-29'}])
        _, log = self.diagnose(show)
        self.assertEqual(log['reason'], 'NO_MISSING_DATES')
        _, log = self.diagnose({'seasons': {}})
        self.assertEqual(log['reason'], 'INVALID_LOCAL_SHAPE')

    def test_import_and_api_exceptions_log_stage_not_exception_text(self):
        secret = 'SENSITIVE_EXCEPTION_SENTINEL'
        with patch.object(tving_dates.importlib, 'import_module', side_effect=ImportError(secret)):
            _, log = self.diagnose()
        self.assertEqual(log['reason'], 'SUPPORT_SITE_UNAVAILABLE')
        for client, expected, stage in [
            (SimpleNamespace(), 'PROGRAM_API_ERROR', 'PROGRAM_API'),
            (SimpleNamespace(get_program_programid=Mock(side_effect=RuntimeError(secret))), 'PROGRAM_API_ERROR', 'PROGRAM_API'),
            (SimpleNamespace(get_program_programid=Mock(return_value={'code': 'P001'}),
                             get_frequency_programid=Mock(side_effect=RuntimeError(secret))), 'PAGE_API_ERROR', 'PAGE_API'),
        ]:
            _, log = self.diagnose(client=client)
            self.assertEqual(log['reason'], expected)
            self.assertEqual(log['stage'], stage)
            self.assertNotIn(secret, json.dumps(log))
        self.assertEqual(log['pages'], [{'page': 1, 'rows': None, 'has_more': 'UNAVAILABLE'}])

    def test_untrusted_values_never_appear_in_logs_and_seasons_are_bounded(self):
        secret = 'SECRET_SENTINEL\nFAKE_LOG token=cookie'
        show = self.show([{'index': 1, 'code': secret, 'title': secret, 'summary': secret}])
        show['seasons'][0]['index'] = secret
        row = self.row(code=secret, day=secret)
        _, log = self.diagnose(show, [{'result': [row], 'has_more': 'N', 'headers': secret}])
        self.assertNotIn('SECRET_SENTINEL', json.dumps(log))
        self.assertEqual(log['seasons'][0]['index_state'], 'UNREPRESENTED')
        _, log = self.diagnose(pages=[{'result': [], 'has_more': secret}])
        self.assertEqual(log['pages'][0]['has_more'], 'INVALID')
        self.assertNotIn('SECRET_SENTINEL', json.dumps(log))
        show = self.show()
        show['seasons'] *= 25
        _, log = self.diagnose(show)
        self.assertEqual(log['season_count'], 25)
        self.assertEqual(len(log['seasons']), 20)
        self.assertTrue(log['seasons_truncated'])

    def test_logging_and_observer_failures_do_not_change_results(self):
        self.logger.info.side_effect = RuntimeError('logger unavailable')
        result = TvingDateEnrichmentTests.run_enrich(self, self.show())
        self.assertEqual(result['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')
        with patch.object(tving_dates._Diagnostics, 'local', side_effect=RuntimeError('observer unavailable')):
            result = TvingDateEnrichmentTests.run_enrich(self, self.show())
        self.assertEqual(result['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')
        with patch.object(tving_dates, '_Diagnostics', side_effect=RuntimeError('construction unavailable')):
            result = TvingDateEnrichmentTests.run_enrich(self, self.show())
        self.assertEqual(result['seasons'][0]['episodes'][0]['originally_available_at'], '2024-02-29')

    def test_invalid_program_missing_class_and_processing_error_codes(self):
        show = self.show()
        self.assertIs(tving_dates.enrich_tving_dates(None, show), show)
        self.assertEqual(json.loads(self.logger.info.call_args.args[0].split(' ', 1)[1])['reason'], 'INVALID_PROGRAM_ID')
        support = ModuleType('support_site')
        with patch.dict(sys.modules, {'support_site': support}):
            self.assertIs(tving_dates.enrich_tving_dates('P001', show), show)
        self.assertEqual(json.loads(self.logger.info.call_args.args[0].split(' ', 1)[1])['reason'], 'SUPPORT_SITE_UNAVAILABLE')
        support.SupportTving = SimpleNamespace(
            get_program_programid=lambda pid: {'code': pid},
            get_frequency_programid=lambda pid, page: {'result': [self.row()], 'has_more': 'N'})
        with patch.dict(sys.modules, {'support_site': support}), \
                patch.object(tving_dates.copy, 'deepcopy', side_effect=RuntimeError('synthetic failure')):
            self.assertIs(tving_dates.enrich_tving_dates('P001', show), show)
        log = json.loads(self.logger.info.call_args.args[0].split(' ', 1)[1])
        self.assertEqual((log['reason'], log['stage'], log['applied']), ('ENRICHMENT_ERROR', 'COPY_APPLY', 0))


if __name__ == '__main__':
    unittest.main()
