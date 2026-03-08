import re, difflib, requests, os, traceback, yaml, copy
from urllib.parse import unquote, quote
import tmdbsimple as tmdb
from .setup import P
logger = P.logger
DEFINE_DEV = False
if os.path.exists(os.path.join(os.path.dirname(__file__), 'mod_basic.py')):
    DEFINE_DEV = True
try:
    if DEFINE_DEV:
        from .get_code import OTTCODE
        from .site_wavve import WAVVE
        from .site_tving import TVING
        from .site_netflix import NF
        from .site_disney import DSNP
        from .site_coupang import COUPANG
        from .site_appletv import ATVP
        from .site_prime import AMZN
        from .site_ebs import EBS
    else:
        from support import SupportSC
        OTTCODE = SupportSC.load_module_P(P, 'get_code').OTTCODE
        WAVVE = SupportSC.load_module_P(P, 'site_wavve').WAVVE
        TVING = SupportSC.load_module_P(P, 'site_tving').TVING
        NF = SupportSC.load_module_P(P, 'site_netflix').NF
        DSNP = SupportSC.load_module_P(P, 'site_disney').DSNP
        COUPANG = SupportSC.load_module_P(P, 'site_coupang').COUPANG
        ATVP = SupportSC.load_module_P(P, 'site_appletv').ATVP
        AMZN = SupportSC.load_module_P(P, 'site_prime').AMZN
        EBS = SupportSC.load_module_P(P, 'site_ebs').EBS
        
except Exception as e:
    P.logger.error(f'Exception:{str(e)}')
    P.logger.error(traceback.format_exc()) 
    
class YAMLUTILS(object):

    @classmethod
    def make_yaml(cls, show_data, target_path=None):
            target_path = P.ModelSetting.get('manual_target')
            tmp = re.sub('[\\/:*?\"<>|]', '', show_data['title']).replace('  ', ' ').replace('[]', '').strip()
            with open(os.path.join(target_path, tmp+'.yaml'), 'w', encoding="utf-8") as outfile:
                if not P.ModelSetting.get_bool('is_primary') and P.ModelSetting.get_bool('delete_title'):
                    del show_data['title']
                yaml.dump(show_data, outfile, sort_keys=False, allow_unicode=True)
                
    @classmethod            
    def code_sort(cls, user_order, url_list):
        if type(user_order) != list:
            try:
                user_order = user_order.split(',')
            except Exception as e: 
                logger.error(f"Exception:{str(e)}")
                logger.error(traceback.format_exc())
        regex_set = {
            'wavve' : r'wavve\.com\/player\/(vod\?contentid=|vod\?programid=.*?)(?P<code>[^#][A-Za-z0-9]+_[A-Za-z0-9]+)', 'tving': r'tving\.(com\/contents)\/(?P<code>[^#].*?)$', 
            'coupang' : r'coupangplay\.com\/titles\/(?P<code>[^/]+)$', 'nf' : r'netflix\.com\/(kr\/title|title)\/(?P<code>[^/#]+)', 'dsnp' : r'disneyplus\.com(\/ko-kr)?\/series\/.*?\/(?P<code>[^?=&]+)',
            'atvp' : r'apple.com/.*?(?P<code>umc.cmc.[a-zA-Z0-9]+)$', 'amzn' : r'primevideo\.com\/detail\/(?P<code>[A-Z0-9]+)', 'amzn' : r'gti\.(?P<code>[a-zA-Z0-9-]+)'
        }
        site_list = ['KW', 'KV', 'KC', 'FN', 'FD', 'FA', 'FP']
        try:
            for order in user_order:
                for url in url_list:
                    match = re.search(regex_set[order.lower()], url)
                    if match:
                        code = site_list[list(regex_set).index(order.lower())]+match.group('code')
                        return code 
        except Exception as e: 
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
            
            
    @classmethod   
    def get_data(cls, code):
        try:
            logger.debug(code)
            site = code[:2]
            code = code[2:]
            logger.debug(f"YAMLUTILS get_data parsed site={site} code={code}")
            site_dict = {'KW' : WAVVE, 'KV' : TVING, 'KC' : COUPANG, 'FN' : NF, 'FD' : DSNP, 'FA' : ATVP, 'FP' : AMZN, 'KE' : EBS}
            show_data = site_dict[site].make_data(code)
            if isinstance(show_data, dict):
                logger.debug(f"YAMLUTILS get_data result site={site} type=dict keys={list(show_data.keys())} seasons={len(show_data.get('seasons', []))}")
            elif isinstance(show_data, list):
                logger.debug(f"YAMLUTILS get_data result site={site} type=list len={len(show_data)}")
            else:
                logger.debug(f"YAMLUTILS get_data result site={site} type={type(show_data).__name__} truthy={bool(show_data)}")
            if P.ModelSetting.get_int('split_season') != 1:   
                season_data = []
                split_season = P.ModelSetting.get_int('split_season')
                for k in range(len(show_data['seasons'])):
                    i = int(show_data['seasons'][k]['index'])
                    for j in range(split_season):
                        episode_data = copy.deepcopy(show_data['seasons'][k]['episodes'])
                        summary = copy.deepcopy(show_data['seasons'][k].get('summary', ''))
                        season_no = int(int(j)*100 + i )                                  
                        season = {
                            'index' : season_no,
                            'summary': summary,
                            'episodes' : episode_data
                        }
                        season_data.append(season)
                show_data['seasons'] = season_data
            return show_data
        except Exception as e: 
            P.logger.error(f"Exception:{e} [site={site if 'site' in locals() else ''} code={code if 'code' in locals() else ''}]")
            P.logger.error(traceback.format_exc())
            
    @classmethod
    def tmdb_data(cls, tmdb_code, show_data):
        from metadata.mod_ftv import ModuleFtv
        tmdbftv = ModuleFtv('metadata')
        data = tmdbftv.info(tmdb_code)
        data = tmdbftv.process_trans('show', data)
        show_data['primary'] = True
        show_data['title'] = data['title']
        show_data['title_sort'] = data['title']
        for art in data['art']:
            if art['aspect'] == 'poster':
                show_data['posters'] = art['value']
                break
        show_data['studio'] = data['studio']
        show_data['original_title'] = data['originaltitle']
        show_data['country'] = data['country']
        show_data['genres'] = data['genre']
        show_data['content_rating'] = data['mpaa']
        show_data['originally_available_at'] = data['premiered']
        for rating in data['ratings']:
            if rating['name'] == 'tmdb':
                show_data['rating'] = rating['value']
                break
        show_data['art'] = data['art']
        actor_list = []
        for actor in data['actor']:
            actor_data = {
                'name' : actor['name'],
                'role' : actor['role'],
                'photo' : actor['image']
            }
            actor_list.append(actor_data)
        show_data['roles'] = actor_list
        show_data['extras'] = data['extra_info']
        for season in show_data['seasons']:
            season_number = season['index']
            season_info = tmdbftv.info(tmdb_code+'_'+str(season_number))
#             season['title'] = season_info['season_name']
            for art in season_info['art']:
                if art['aspect'] == 'poster':
                    season['posters'] = art['value']
                    break
            season['summary'] = season_info['plot']
            for episode in season['episodes']:
                try:
                    episode['originally_available_at'] = season_info['episodes'][episode['index']]['premiered']
                except:
                    episode['originally_available_at'] = ''
                try:        
                    episode['thumbs'] = season_info['episodes'][episode['index']]['art'][0]   
                except:
                    episode['thumbs'] = ''
                try:
                    episode['writers'] = str(season_info['episodes'][episode['index']]['writer'])[1:-1].replace("'",'').strip()
                except:
                    episode['writers'] = ''
                try:
                    episode['directors'] = str(season_info['episodes'][episode['index']]['director'])[1:-1].replace("'",'').strip()
                except:
                    episode['directors'] = ''
        return show_data
