import os, json, re, base64
import requests

ARTISTA           = os.environ['ARTISTA']
LASTFM_API_KEY    = os.environ.get('LASTFM_API_KEY', '')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')

def get_spotify_token():
    try:
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET}".encode()).decode()
        r = requests.post("https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"})
        return r.json().get('access_token')
    except:
        return None

def get_spotify_info(nom, artista, token):
    """Retorna (any, cover_url) de Spotify per la cançó."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        query = f"track:{nom} artist:{artista}"
        r = requests.get(
            f"https://api.spotify.com/v1/search?q={requests.utils.quote(query)}&type=track&limit=1",
            headers=headers
        )
        items = r.json().get('tracks', {}).get('items', [])
        if items:
            album = items[0]['album']
            date = album.get('release_date', '')
            any_canco = int(date[:4]) if date and len(date) >= 4 else 0
            cover_url = album['images'][0]['url'] if album.get('images') else None
            return any_canco, cover_url
    except:
        pass
    return 0, None

def buscar_evolucio(artista, api_key, sp_token):
    print("Buscant tracks via Last.fm...")
    r = requests.get(
        f"https://ws.audioscrobbler.com/2.0/?method=artist.gettoptracks&artist={requests.utils.quote(artista)}&api_key={api_key}&format=json&limit=100"
    )
    data = r.json()
    top_tracks = data.get('toptracks', {}).get('track', [])
    print(f"Top tracks Last.fm: {len(top_tracks)}")
    if not top_tracks:
        return []

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

        any_canco, cover_url = get_spotify_info(nom, artista, sp_token)

        if any_canco > 0:
            tracks_amb_any.append({'nom': nom, 'any': any_canco, 'popularitat': popularitat})
            print(f"   {any_canco} - {nom}")

    # Agrupar per any i quedar-nos amb la MÉS POPULAR de cada any
    per_any = {}
    for t in tracks_amb_any:
        a = t['any']
        if a not in per_any or t['popularitat'] > per_any[a]['popularitat']:
            per_any[a] = t

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

print("Obtenint token de Spotify...")
sp_token = get_spotify_token()
print("Token OK" if sp_token else "Sense token Spotify")

tracks = buscar_evolucio(ARTISTA, LASTFM_API_KEY, sp_token)

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
