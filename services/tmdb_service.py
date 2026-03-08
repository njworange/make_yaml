def apply_tmdb_data(tmdb_code, show_data):
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
        actor_list.append({
            'name': actor['name'],
            'role': actor['role'],
            'photo': actor['image'],
        })
    show_data['roles'] = actor_list
    show_data['extras'] = data['extra_info']
    for season in show_data['seasons']:
        season_info = tmdbftv.info(tmdb_code + '_' + str(season['index']))
        for art in season_info['art']:
            if art['aspect'] == 'poster':
                season['posters'] = art['value']
                break
        season['summary'] = season_info['plot']
        for episode in season['episodes']:
            try:
                episode['originally_available_at'] = season_info['episodes'][episode['index']]['premiered']
            except Exception:
                episode['originally_available_at'] = ''
            try:
                episode['thumbs'] = season_info['episodes'][episode['index']]['art'][0]
            except Exception:
                episode['thumbs'] = ''
            try:
                episode['writers'] = str(season_info['episodes'][episode['index']]['writer'])[1:-1].replace("'", '').strip()
            except Exception:
                episode['writers'] = ''
            try:
                episode['directors'] = str(season_info['episodes'][episode['index']]['director'])[1:-1].replace("'", '').strip()
            except Exception:
                episode['directors'] = ''
    return show_data
