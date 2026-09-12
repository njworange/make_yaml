"""Synthetic offline fixtures; not live OTT, .pyf or FlaskFarm integration tests.

Run: python3 -B -m unittest discover -s tests -v
The writer is imported with a stub setup module. Provider functions are extracted
from the actual source AST to avoid loading opaque legacy modules or doing I/O.
"""

import ast
import copy
import html
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


if __name__ == '__main__':
    unittest.main()
