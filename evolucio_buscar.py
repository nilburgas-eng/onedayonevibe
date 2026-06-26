import os, json, re, time
import requests

ARTISTA        = os.environ['ARTISTA']
LASTFM_API_KEY = os.environ.get('LASTFM_API_KEY', '')

def buscar_evolucio(artista, api_key):
    print("Buscant tracks via Last.fm...")
    r = requests.get(
        f"https://ws.audioscrobbler.com/2.0/?method=artist.gettoptracks&artist={requests.utils.quote(artista)}&api_key={api_key}&format=json&limit=100"
    )
    data = r.json()
    top_tracks = data.get('toptracks', {}).get('track', [])
    print(f"Top tracks Last.fm: {len(top_tracks)}")

    if not top_tracks:
        return []

    # Per cada track popular, trobar l'any via MusicBrainz
    tracks_amb_any = []
    vistes = set()

    for t in top_tracks[:40]:
        nom = t['name']
        key_norm = re.sub(r'\s*[\(\[].*?[\)\]]', '', nom.lower())
        key_norm = re.sub(r'\s*-\s*.*$', '', key_norm).strip()
        if key_norm in vistes:
            continue
        vistes.add(key_norm)

        popularitat = int(t.get('playcount', 0))
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

        if any_canco > 0:
            tracks_amb_any.append({'nom': nom, 'any': any_canco, 'popularitat': popularitat})

    # Agrupar per any i quedar-nos amb la MÉS POPULAR de cada any
    per_any = {}
    for t in tracks_amb_any:
        a = t['any']
        if a not in per_any or t['popularitat'] > per_any[a]['popularitat']:
            per_any[a] = t

    # Ordenar cronològicament (antic -> nou)
    anys_ordenats = sorted(per_any.keys())

    tracks = []
    pos = 1
    for a in anys_ordenats:
        if len(tracks) >= 10:
            break
        t = per_any[a]
        tracks.append({
            'pos': pos,
            'nom': t['nom'],
            'any': t['any'],
            'cover_url': None,
            'timestamp_manual': None,
            'nom_manual': None,
            'yt_url': None
        })
        pos += 1

    return tracks

tracks = buscar_evolucio(ARTISTA, LASTFM_API_KEY)

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

print(f"\nEvolucio trobada ({len(tracks)} anys):")
for t in tracks:
    print(f"  #{t['pos']}: {t['any']} - {t['nom']}")

data = {
    'artista': ARTISTA,
    'tracks': tracks
}
with open('evolucio_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\nevolucio_data.json escrit!")
