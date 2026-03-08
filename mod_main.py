from flask import render_template, jsonify
from plugin import PluginModuleBase
from tool import ToolUtil
from .providers.legacy_registry import get_ottcode_class
from .services.input_service import build_direct_code, get_site_name, resolve_search_keyword, resolve_search_parts
from .services.schema_validator import has_korean_last_episode, has_show_data
from .setup import P
from .yaml_utils import YAMLUTILS
import re, os, traceback
import requests
from html import unescape
logger = P.logger
OTTCODE = get_ottcode_class()

name = 'main'

class ModuleMain(PluginModuleBase):
    
    db_default = {
        f'{name}_db_version' : '1',
        f'ftv_first_order' : 'WAVVE, TVING, COUPANG, NF, DSNP, AMZN, ATVP',
        f'is_primary' : 'false',
        f'match_score' : '95',
        f'extra_season' : 'True',
        f'ep_thum' : 'false',
        f'split_season' : '1',
        f'delete_title' : 'True',
        f'manual_target' : '',
        f'use_proxy' : 'False',
        f'proxy_url' : '',
        f'chrome_url': '',
    }
    
    def __init__(self, P):
        super(ModuleMain, self).__init__(P, name=name, first_menu='main')

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg["package_name"] = P.package_name
        arg["module_name"] = self.name
        if sub == "setting":
            return render_template(f"{P.package_name}_{self.name}_{sub}.html", arg=arg)
        return render_template(f"{P.package_name}_{self.name}.html", arg=arg, sub=sub)
    
    def convert_title_format(self, original_title):
        # 정규 표현식을 사용하여 제목과 연도를 추출
        match = re.match(r'(.*) \((\d{4})\)', original_title)
        if match:
            title = match.group(1)
            year = match.group(2)
            return f"{title}|{year}"
        else:
            return None
            
    def disney_redirect(self, code):
        code = code.strip()
        fallback_code = code
        request_url = ''
        logger.debug(f"DSNP redirect start raw={code}")
        if 'disneyplus.com' in code:
            url = code
            request_url = url.split('?', 1)[0]
            match = re.search(r'/series/.*?/(?P<code>[^?&#/]+)', code)
            if match:
                logger.debug(f"DSNP redirect direct series code={match.group('code')}")
                return match.group('code')
            match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', code)
            if match:
                fallback_code = match.group('code').replace('entity-', '', 1)
        else:
            fallback_code = re.sub(r'^entity-', '', code)
            url = 'https://www.disneyplus.com/ko-kr/browse/entity-' + fallback_code
            request_url = url
        logger.debug(f"DSNP redirect prepared fallback={fallback_code} request_url={request_url}")

        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "sec-ch-ua": "\"Google Chrome\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.disneyplus.com",
            "Referer": "https://www.disneyplus.com/",
        }
        try:
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            logger.debug(f"DSNP redirect response final_url={response.url.split('?', 1)[0]} history={len(response.history)}")
            match = re.search(r'disneyplus\.com(\/ko-kr)?\/series\/.*?\/(?P<code>[^?=&/]+)', response.url)
            if match:
                logger.debug(f"DSNP redirect resolved series code={match.group('code')}")
                return match.group('code')
            match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', response.url)
            if match:
                browse_code = match.group('code').replace('entity-', '', 1)
                logger.debug(f"DSNP redirect browse fallback code={browse_code}")
                resolved_code = self.resolve_disney_code_from_html(response.text, browse_code)
                if resolved_code:
                    logger.debug(f"DSNP redirect resolved code from HTML={resolved_code}")
                    return resolved_code
                return browse_code
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
        logger.debug(f"DSNP redirect returning fallback={fallback_code}")
        return fallback_code

    def extract_disney_page_metadata(self, html):
        title = ''
        description = ''
        patterns = [
            (r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', 'title'),
            (r'<meta[^>]+name=["\']title["\'][^>]+content=["\']([^"\']+)', 'title'),
            (r'<title>([^<]+)</title>', 'title'),
            (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)', 'description'),
            (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', 'description'),
        ]
        for pattern, key in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                value = unescape(match.group(1)).strip()
                if key == 'title' and not title:
                    title = value
                elif key == 'description' and not description:
                    description = value
        return title, description

    def normalize_disney_title(self, title):
        title = unescape(title).strip()
        title = re.sub(r'\s*\|\s*디즈니\+.*$', '', title)
        title = re.sub(r'\s*\|\s*Disney\+.*$', '', title)
        title = re.sub(r'^Watch\s+', '', title)
        return title.strip()

    def disney_title_key(self, title):
        title = self.normalize_disney_title(title)
        return re.sub(r'[^0-9A-Za-z가-힣]+', '', title).lower()

    def resolve_disney_code_from_html(self, html, fallback_code):
        title, description = self.extract_disney_page_metadata(html)
        normalized_title = self.normalize_disney_title(title)
        logger.debug(f"DSNP HTML metadata title={normalized_title} description_len={len(description)} fallback_code={fallback_code}")
        if not normalized_title:
            return None
        try:
            ottcode = OTTCODE(normalized_title)
            ottcode_list = ottcode.get_ott_code()
            logger.debug(f"DSNP HTML metadata OTT search count={len(ottcode_list) if ottcode_list else 0}")
            resolved = YAMLUTILS.code_sort(['DSNP'], ottcode_list)
            logger.debug(f"DSNP HTML metadata resolved candidate={resolved}")
            if resolved and resolved.startswith('FD'):
                show_data = YAMLUTILS.get_data(resolved)
                expected_key = self.disney_title_key(normalized_title)
                candidate_titles = []
                if isinstance(show_data, dict):
                    candidate_titles.extend([
                        show_data.get('title', ''),
                        show_data.get('original_title', ''),
                        show_data.get('title_sort', ''),
                    ])
                candidate_keys = [self.disney_title_key(x) for x in candidate_titles if x]
                logger.debug(f"DSNP HTML metadata candidate_keys={candidate_keys} expected_key={expected_key}")
                if expected_key and expected_key in candidate_keys:
                    return resolved[2:]
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
        return None

    def is_disney_entity_code(self, code):
        code = re.sub(r'^entity-', '', code.strip())
        return re.match(r'^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$', code) is not None
        
    def process_command(self, command, arg1, arg2, arg3, req):
        self.code = ''
        arg1 = arg1.strip()
        if command == 'search_keyword':
            self.code, ottcode = resolve_search_keyword(arg1)
            if self.code is None:
                return jsonify({"msg":"검색어 실패", "ret":"fail"})
        elif command == 'auto_target':
            source = arg1
            source_list = os.listdir(source)
            for f in source_list:
                #if f in ['가', '나', '다', '라','마','바']:
                    char = os.path.join(source, f)
                    if os.path.isdir(char):
                        char_list = os.listdir(char)
                        for t in char_list:
                            
                            try:
                                target = os.path.join(char,t)
                                if os.path.isdir(target) and not os.path.isfile(os.path.join(target, "show.yaml")):
                                    folder = os.path.basename(target)
                                    keyword = self.convert_title_format(folder)
                                    keyword = keyword.split('|')
                                    if keyword:
                                        self.code, ottcode = resolve_search_parts(keyword)
                                        if self.code:
                                            show_data = YAMLUTILS.get_data(self.code)
                                            if has_korean_last_episode(show_data):
                                                YAMLUTILS.make_yaml(show_data, target)
                                        else:
                                            continue
                            except:
                                print("오류발생:", target)
                                continue

        elif command == 'wavve_code':
            self.code = 'KW'+arg1
        elif command == 'tving_code':
            self.code = 'KV'+arg1
        elif command == 'cpang_code':
            self.code = 'KC'+arg1
        elif command == 'nf_code':
            self.code = 'FN'+arg1
        elif command == 'dsnp_code':
            needs_redirect = 'disneyplus.com' in arg1 or arg1.startswith('entity-')
            logger.debug(f"DSNP command received arg1={arg1} arg2={arg2} needs_redirect_initial={needs_redirect} is_entity={self.is_disney_entity_code(arg1)}")
            if not needs_redirect and self.is_disney_entity_code(arg1):
                needs_redirect = True
            if needs_redirect:
                arg1 = self.disney_redirect(arg1)
                logger.debug(f"DSNP command redirected arg1={arg1} unresolved_entity={self.is_disney_entity_code(arg1)}")
                if self.is_disney_entity_code(arg1):
                    if arg2 == 'test':
                        return jsonify({'ret':'fail', 'msg':'디즈니 시리즈 코드 확인 실패', 'json': []})
                    return jsonify({'msg':'검색 실패', 'ret':'fail'})
            self.code = 'FD'+arg1
        else:
            self.code = build_direct_code(command, arg1)
        if self.code != '' and self.code != None :
            site = self.code[:2]
            logger.debug(f"Command {command} executing code={self.code} mode={arg2}")
            show_data = YAMLUTILS.get_data(self.code)
            if arg2 == 'test':
                return jsonify({'ret':'success', 'json': show_data})
            elif has_show_data(show_data):
                if has_korean_last_episode(show_data):
                    if P.ModelSetting.get_bool('is_primary'):
                        self.tmdb_code = 'FT'+str(ottcode.tmdb_search()) 
                        show_data = YAMLUTILS.tmdb_data(self.tmdb_code, show_data)
                    YAMLUTILS.make_yaml(show_data)
                    return jsonify({"msg":f"{get_site_name(site)} 코드 실행", "ret":"success"})
                else:
                    return jsonify({"msg":f"{get_site_name(site)} 한글 메타데이터 아님", "ret":"fail"})
            else:
                return jsonify({"msg":"검색 실패", "ret":"fail"})
        else:
            return jsonify({"msg":"검색 실패", "ret":"fail"})
    
