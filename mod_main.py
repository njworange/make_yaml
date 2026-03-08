from flask import render_template, jsonify
from plugin import PluginModuleBase
from tool import ToolUtil
from .providers.legacy_registry import get_ottcode_class, is_command_enabled
from .services.disney_service import handle_disney_command
from .services.input_service import build_direct_code, get_site_name, resolve_search_keyword, resolve_search_parts
from .services.schema_validator import has_korean_last_episode, has_show_data
from .setup import P
from .yaml_utils import YAMLUTILS
import re, os
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
            
    def process_command(self, command, arg1, arg2, arg3, req):
        self.code = ''
        ottcode = None
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

        elif command in ['wavve_code', 'tving_code', 'cpang_code', 'nf_code', 'amzn_code', 'atvp_code', 'ebskids_code']:
            if not is_command_enabled(command):
                return jsonify({"msg":"현재 지원하지 않는 OTT", "ret":"fail"})
            self.code = build_direct_code(command, arg1)
        elif command == 'dsnp_code':
            if not is_command_enabled(command):
                return jsonify({"msg":"현재 지원하지 않는 OTT", "ret":"fail"})
            self.code, response = handle_disney_command(arg1, arg2)
            if response is not None:
                return response
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
                    if P.ModelSetting.get_bool('is_primary') and ottcode is not None:
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
    
