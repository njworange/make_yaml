from flask import render_template, jsonify
from plugin import PluginModuleBase
from tool import ToolUtil
from .setup import P
from support_site import SiteUtil
from .yaml_utils import YAMLUTILS
import re, os, traceback
import requests
logger = P.logger
DEFINE_DEV = False
if os.path.exists(os.path.join(os.path.dirname(__file__), 'get_code.py')):
    DEFINE_DEV = True
try:
    if DEFINE_DEV:
        from .get_code import OTTCODE
    else:
        from support import SupportSC
        OTTCODE = SupportSC.load_module_P(P, 'get_code').OTTCODE

except Exception as e:
    P.logger.error(f'Exception:{str(e)}')
    P.logger.error(traceback.format_exc())

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
        if 'disneyplus.com' in code:
            url = code
            match = re.search(r'/series/.*?/(?P<code>[^?&#/]+)', code)
            if match:
                return match.group('code')
            match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', code)
            if match:
                fallback_code = match.group('code').replace('entity-', '', 1)
        else:
            fallback_code = re.sub(r'^entity-', '', code)
            url = 'https://www.disneyplus.com/ko-kr/browse/entity-' + fallback_code

        headers = {
            "sec-ch-ua-platform": "\"Windows\"",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "sec-ch-ua": "\"Google Chrome\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.disneyplus.com",
            "Referer": "https://www.disneyplus.com/",
        }
        try:
            response = requests.get(url, headers=headers, allow_redirects=True)
            match = re.search(r'disneyplus\.com(\/ko-kr)?\/series\/.*?\/(?P<code>[^?=&/]+)', response.url)
            if match:
                return match.group('code')
            match = re.search(r'/browse/(?P<code>entity-[^?&#/]+)', response.url)
            if match:
                return match.group('code').replace('entity-', '', 1)
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
        return fallback_code
        
    def process_command(self, command, arg1, arg2, arg3, req):
        self.code = ''
        arg1 = arg1.strip()
        if command == 'search_keyword':
            keyword = arg1.split('|')
            if len(keyword) == 1:
                ottcode = OTTCODE(keyword[0].strip())
                ottcode_list = ottcode.get_ott_code()
                user_order = P.ModelSetting.get_list('ftv_first_order', ',')
                self.code = YAMLUTILS.code_sort(user_order, ottcode_list)
            elif len(keyword) == 2:
                ottcode = OTTCODE(keyword[0].strip(), keyword[1].strip())
                ottcode_list = ottcode.get_ott_code()
                user_order = P.ModelSetting.get_list('ftv_first_order', ',')
                self.code = YAMLUTILS.code_sort(user_order, ottcode_list)
            else:
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
                                        ottcode = OTTCODE(keyword[0].strip(), keyword[1].strip())
                                        ottcode_list = ottcode.get_ott_code()
                                        user_order = P.ModelSetting.get_list('ftv_first_order', ',')
                                        self.code = YAMLUTILS.code_sort(user_order, ottcode_list)
                                        if self.code:
                                            show_data = YAMLUTILS.get_data(self.code)
                                            if SiteUtil.is_include_hangul(show_data['seasons'][-1]['episodes'][-1]['title']) or SiteUtil.is_include_hangul(show_data['seasons'][-1]['episodes'][-1]['summary']) :
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
            if not needs_redirect and re.match(r'^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$', arg1):
                needs_redirect = True
            if needs_redirect:
                arg1 = self.disney_redirect(arg1)
            self.code = 'FD'+arg1
        elif command == 'amzn_code':
            self.code = 'FP'+arg1
        elif command == 'atvp_code':
            self.code = 'FA'+arg1
        elif command == 'ebskids_code':
            self.code = 'KE'+arg1
        if self.code != '' and self.code != None :
            site = self.code[:2]
            site_name_dict = {
                'KW' : '웨이브', 'KV' : '티빙', 'KC' : '쿠팡 플레이', 'FN' : '넷플릭스', 'FD' : '디즈니 플러스', 'FP' : '프라임 비디오', 'FA' : '애플TV', 'KE' : 'EBS',
            }
            show_data = YAMLUTILS.get_data(self.code)
            if arg2 == 'test':
                return jsonify({'ret':'success', 'json': show_data})
            elif show_data !=[]:
                if SiteUtil.is_include_hangul(show_data['seasons'][-1]['episodes'][-1]['title']) or SiteUtil.is_include_hangul(show_data['seasons'][-1]['episodes'][-1]['summary']) :
                    if P.ModelSetting.get_bool('is_primary'):
                        self.tmdb_code = 'FT'+str(ottcode.tmdb_search()) 
                        show_data = YAMLUTILS.tmdb_data(self.tmdb_code, show_data)
                    YAMLUTILS.make_yaml(show_data)
                    return jsonify({"msg":f"{site_name_dict[site]} 코드 실행", "ret":"success"})
                else:
                    return jsonify({"msg":f"{site_name_dict[site]} 한글 메타데이터 아님", "ret":"fail"})
            else:
                return jsonify({"msg":"검색 실패", "ret":"fail"})
        else:
            return jsonify({"msg":"검색 실패", "ret":"fail"})
    
