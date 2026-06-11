import os, json, re, time
import requests

ARTISTA        = os.environ['ARTISTA']
ANY_TALL       = int(os.environ.get('ANY_TALL', '2018'))
LASTFM_API_KEY = os.environ.get('LASTFM_API_KEY', '')

def buscar_tracks_lastfm(artista, any_tall, api_key):
    print("Buscant tracks via Last.fm...")
    r = requests.get(
        f"https://ws.audioscrobbler.com/2.0/?method=artist.gettoptracks&artist={requests.utils.quote(artista)}&api_key={api_key}&format=json&limit=50"
    )
    data = r.json()
    top_tracks = data.get('toptracks', {}).get('track', [])
    print(f"Top tracks Last.fm: {len(top_tracks)}")

    if not top_tracks:
        return []

    tracks_amb_any = []
    vistes = set()

    for t in top_tracks[:30]:
        nom = t['name']
        key_norm = re.sub(r'\s*[\(\[].*?[\)\]]', '', nom.lower())
        key_norm = re.sub(r'\s*-\s*.*$', '', key_norm).strip()
        if key_norm in vistes:
            continue
        vistes.add(key_norm)

        any_canco = 0
        try:
            mb = requests.get(
                f"https://musicbrainz.org/ws/2/recording/?query=recording:{requests.utils.quote(nom)}+artist:{requests.utils.quote(artista)}&fmt=json&limit=1",
                headers={"User-Agent": "onedayonevibe/1.0 (nilburgas@gmail.com)"}
            )
            recordings = mb.json().get('recordings', [])
            if recordings:
                date = recordings[0].get('first-release-date', '')
                if date:
                    any_canco = int(date[:4])
            time.sleep(0.3)
        except:
            pass

        tracks_amb_any.append({'nom': nom, 'any': any_canco})

    then_list = [t for t in tracks_amb_any if 0 < t['any'] < any_tall]
    now_list  = [t for t in tracks_amb_any if t['any'] >= any_tall]

    if not then_list and not now_list:
        mid = len(tracks_amb_any) // 2
        then_list = tracks_amb_any[:mid]
        now_list  = tracks_amb_any[mid:]
        print("Anys no disponibles — distribuint per ordre")

    n = min(len(then_list), len(now_list), 5)
    if n == 0:
        print(f"AVIS: una era buida (THEN:{len(then_list)} NOW:{len(now_list)})")
        then_list = then_list[:5]
        now_list  = now_list[:5]
    else:
        then_list = then_list[:n]
        now_list  = now_list[:n]

    print(f"THEN: {len(then_list)} · NOW: {len(now_list)} (equilibrat a {n} cada un)")

    tracks = []
    pos = 1
    max_len = max(len(then_list), len(now_list))
    for i in range(max_len):
        if i < len(then_list) and len(tracks) < 10:
            tracks.append({
                'pos': pos, 'nom': then_list[i]['nom'], 'any': then_list[i]['any'],
                'era': 'THEN', 'cover_url': None,
                'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
            })
            pos += 1
        if i < len(now_list) and len(tracks) < 10:
            tracks.append({
                'pos': pos, 'nom': now_list[i]['nom'], 'any': now_list[i]['any'],
                'era': 'NOW', 'cover_url': None,
                'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
            })
            pos += 1

    return tracks

tracks = buscar_tracks_lastfm(ARTISTA, ANY_TALL, LASTFM_API_KEY)

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

print(f"\nTracks trobats ({len(tracks)}):")
for t in tracks:
    print(f"  [{t['era']}] #{t['pos']}: {t['nom']} ({t['any']})")

data = {
    'artista': ARTISTA,
    'any_tall': ANY_TALL,
    'tracks': tracks
}
with open('thenvsnow_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\nthenvsnow_data.json escrit!")
