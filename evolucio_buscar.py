# evolucio_buscar.py - busca els temes mes populars de l'artista (Last.fm) i n'esbrina l'any ORIGINAL (Spotify).
# Millores: l'any es el mes antic entre les versions del mateix tema (no el d'una recopilacio), i si hi ha mes de 10 anys
# es trien 10 de repartits per tota la trajectoria (sempre el primer i l'ultim), no els 10 primers.
import os, json, re, time, base64, unicodedata
import requests

ARTISTA           = os.environ['ARTISTA']
LASTFM_API_KEY    = os.environ.get('LASTFM_API_KEY', '')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')

MAX_TEMES_VIDEO = 10     # quants temes (anys) surten al video
TOP_LASTFM      = 60     # quants temes populars es consulten a Spotify


def sense_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s or '')) if unicodedata.category(c) != 'Mn').lower()


def titol_base(s):
    """'Sky (Radio Edit)' / 'Sky - Extended Mix' / 'Sky feat. X' -> 'sky'"""
    s = sense_accents(s)
    s = re.sub(r'\s*[\(\[].*?[\)\]]', '', s)
    s = re.sub(r'\s+-\s+.*$', '', s)
    s = re.sub(r'\s+(feat\.?|ft\.?|featuring)\s+.*$', '', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def get_spotify_token():
    try:
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET}".encode()).decode()
        r = requests.post("https://accounts.spotify.com/api/token",
                          headers={"Authorization": f"Basic {creds}"},
                          data={"grant_type": "client_credentials"}, timeout=20)
        return r.json().get('access_token')
    except Exception as e:
        print(f"   (error token Spotify: {e})")
        return None


def spotify_get(url, params, token):
    for intent in range(4):
        try:
            r = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        except Exception as e:
            print(f"   (error de xarxa: {e})")
            return None
        if r.status_code == 429:
            espera = min(int(r.headers.get('Retry-After', '2') or 2) + 1, 30)
            print(f"   (Spotify 429, espero {espera}s)")
            time.sleep(espera)
            continue
        if r.status_code != 200:
            return None
        return r.json()
    return None


def any_original(nom, artista, token):
    """Any mes antic entre les versions de Spotify que son del mateix tema i del mateix artista (0 si no se'n troba cap)."""
    base = titol_base(nom)
    art = sense_accents(artista)
    anys, anys_recopilacio = [], []
    for q in (f'track:"{nom}" artist:"{artista}"', f'{nom} {artista}'):
        d = spotify_get("https://api.spotify.com/v1/search", {"q": q, "type": "track", "limit": 10}, token)
        if not d:
            continue
        for it in d.get('tracks', {}).get('items', []):
            if titol_base(it.get('name')) != base:
                continue
            if not any(art in sense_accents(a.get('name')) or sense_accents(a.get('name')) in art for a in it.get('artists', [])):
                continue
            album = it.get('album', {})
            data = album.get('release_date', '')
            if not (data and len(data) >= 4 and data[:4].isdigit()):
                continue
            (anys_recopilacio if album.get('album_type') == 'compilation' else anys).append(int(data[:4]))
        if anys:
            break
    llista = anys or anys_recopilacio
    return min(llista) if llista else 0


def triar_repartits(llista, n):
    """Si hi ha mes de n elements, en tria n repartits uniformement (inclou el primer i l'ultim)."""
    if len(llista) <= n:
        return llista
    idxs = sorted(set(round(i * (len(llista) - 1) / (n - 1)) for i in range(n)))
    return [llista[i] for i in idxs]


def buscar_evolucio(artista, api_key, sp_token):
    print("Buscant tracks via Last.fm...")
    r = requests.get(
        f"https://ws.audioscrobbler.com/2.0/?method=artist.gettoptracks&artist={requests.utils.quote(artista)}&api_key={api_key}&format=json&limit=100",
        timeout=30)
    data = r.json()
    top_tracks = data.get('toptracks', {}).get('track', [])
    print(f"Top tracks Last.fm: {len(top_tracks)}")
    if not top_tracks:
        return []

    tracks_amb_any = []
    vistes = set()
    for t in top_tracks[:TOP_LASTFM]:
        nom = t['name']
        key_norm = titol_base(nom)
        if not key_norm or key_norm in vistes:
            continue
        vistes.add(key_norm)
        popularitat = int(t.get('playcount', 0) or 0)
        any_canco = any_original(nom, artista, sp_token) if sp_token else 0
        if any_canco > 0:
            tracks_amb_any.append({'nom': nom, 'any': any_canco, 'popularitat': popularitat})
            print(f"   {any_canco} - {nom}")
        else:
            print(f"   ?    - {nom} (sense any a Spotify)")
        time.sleep(0.1)

    # el mes popular de cada any
    per_any = {}
    for t in tracks_amb_any:
        a = t['any']
        if a not in per_any or t['popularitat'] > per_any[a]['popularitat']:
            per_any[a] = t

    anys_ordenats = sorted(per_any.keys())
    print(f"\nAnys amb tema: {anys_ordenats}")
    triats = triar_repartits([per_any[a] for a in anys_ordenats], MAX_TEMES_VIDEO)
    tracks = []
    for pos, t in enumerate(triats, start=1):
        tracks.append({
            'pos': pos,
            'nom': t['nom'],
            'any': t['any'],
            'cover_url': None,
            'timestamp_manual': None,
            'nom_manual': None,
            'yt_url': None
        })
    return tracks


print("Obtenint token de Spotify...")
sp_token = get_spotify_token()
print("Token OK" if sp_token else "Sense token Spotify")

tracks = buscar_evolucio(ARTISTA, LASTFM_API_KEY, sp_token)

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

if len(tracks) < 4:
    print(f"AVIS: nomes {len(tracks)} anys diferents. Pots afegir o canviar anys a mà a la web abans de generar.")

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
