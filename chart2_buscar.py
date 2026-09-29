import os, json, re
import requests

GENERE = os.environ.get('GENERE', 'electronica')
TIDAL_PLAYLIST_ID = "d57a8f2c-4158-44b7-aa7f-4ba4314c1ba8"  # 40 Biggest EDM/DANCE Hits Weekly

def get_tidal_token():
    client_id = os.environ.get('TIDAL_CLIENT_ID', '')
    client_secret = os.environ.get('TIDAL_CLIENT_SECRET', '')
    r = requests.post(
        "https://auth.tidal.com/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret)
    )
    r.raise_for_status()
    return r.json()['access_token']

def scrape_electronica_tidal():
    print(f"Consultant playlist de Tidal: {TIDAL_PLAYLIST_ID}")
    token = get_tidal_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.api+json"
    }
    r = requests.get(
        f"https://openapi.tidal.com/v2/playlists/{TIDAL_PLAYLIST_ID}",
        headers=headers,
        params={"countryCode": "US", "include": "items"}
    )
    r.raise_for_status()
    data = r.json()

    # DEBUG: si l'estructura no encaixa com esperem, aixo ens dira com es la resposta real
    print("DEBUG claus arrel:", list(data.keys()))
    if 'included' in data:
        tipus_inclosos = set(item.get('type') for item in data['included'])
        print("DEBUG tipus a 'included':", tipus_inclosos)

    # Mapa d'items inclosos (tracks i artistes) per id, format JSON:API
    inclosos = {(item['type'], item['id']): item for item in data.get('included', [])}

    ordre_items = data.get('data', {}).get('relationships', {}).get('items', {}).get('data', [])

    tracks = []
    pos = 1
    for ref in ordre_items:
        if pos > 10:
            break
        track = inclosos.get((ref.get('type'), ref.get('id')))
        if not track:
            continue
        attrs = track.get('attributes', {})
        nom = attrs.get('title')
        if not nom:
            continue

        artista = ''
        rel_artistes = track.get('relationships', {}).get('artists', {}).get('data', [])
        if rel_artistes:
            art = inclosos.get((rel_artistes[0].get('type'), rel_artistes[0].get('id')))
            if art:
                artista = art.get('attributes', {}).get('name', '')

        tracks.append({
            'pos': pos, 'nom': nom, 'artista': artista, 'cover_url': None,
            'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
        })
        pos += 1

    import datetime
    avui = datetime.date.today()
    dilluns = avui - datetime.timedelta(days=avui.weekday())
    setmana_text = f"WEEK OF {dilluns.strftime('%B %d, %Y').upper()}"

    return tracks, setmana_text

def scrape_electronica_dancecharts():
    url = "https://www.dance-charts.de/djcharts"
    print(f"Scraping electronica: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers, timeout=30).text

    import datetime
    avui = datetime.date.today()
    dilluns = avui - datetime.timedelta(days=avui.weekday())
    setmana_text = f"WEEK OF {dilluns.strftime('%B %d, %Y').upper()}"

    tracks = []
    # Cada cancó del rànquing te un enllaç /songinfos/ID-slug; el dividim per aquest
    # patró per aïllar cada bloc i extreure'n titol, artista i (si hi es) l'enllaç de YouTube.
    blocs = re.split(r'href="(?:https://www\.dance-charts\.de)?/songinfos/(\d+)-[\w-]+"', html)
    vistos = set()
    for i in range(1, len(blocs), 2):
        if len(tracks) >= 10:
            break
        song_id = blocs[i]
        if song_id in vistos:
            continue
        abans = blocs[i - 1][-500:] if i - 1 >= 0 else ''
        despres = blocs[i + 1][:1000] if i + 1 < len(blocs) else ''

        m_titol = re.search(r'title="([^"]+)"', despres[:300])
        titol = html_unescape(m_titol.group(1)) if m_titol else None

        m_yt = re.search(r'(https://www\.youtube\.com/watch\?v=[\w-]+)', despres)
        yt_url = m_yt.group(1) if m_yt else None

        m_art = re.search(r'([A-ZÀ-Ü0-9][A-ZÀ-Ü0-9 &.,\'\-]{2,70})\s*$', abans.strip())
        artista = html_unescape(m_art.group(1)) if m_art else ''

        if titol:
            vistos.add(song_id)
            tracks.append({
                'pos': len(tracks) + 1, 'nom': titol, 'artista': artista, 'cover_url': None,
                'timestamp_manual': None, 'nom_manual': None, 'yt_url': yt_url
            })

    return tracks, setmana_text

def html_unescape(s):
    s = s.replace('&amp;', '&').replace('&#039;', "'").replace('&#39;', "'")
    s = s.replace('&quot;', '"').replace('&nbsp;', ' ')
    return s.strip()

def scrape_hardstyle():
    url = "https://hardstyle.com/en/charts?genre=hardstyle"
    print(f"Scraping hardstyle: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text

    import datetime
    avui = datetime.date.today()
    dilluns = avui - datetime.timedelta(days=avui.weekday())
    setmana_text = f"WEEK OF {dilluns.strftime('%B %d, %Y').upper()}"


    tracks = []
    # Cada cançó és un bloc <div class="track listView ..." data-track-id="UUID">
    # El dividim per data-track-id per aïllar cada cançó
    blocs = re.split(r'data-track-id="([\w-]+)"', html)
    # blocs alterna: [text, uuid, text, uuid, ...]
    vistos = set()
    pos = 1
    for i in range(1, len(blocs), 2):
        if pos > 10:
            break
        uuid = blocs[i]
        if uuid in vistos:
            continue
        contingut = blocs[i+1] if i+1 < len(blocs) else ''
        bloc = contingut[:3000]

        # Títol: <a class="linkTitle trackTitle" ... title="TITOL">
        m_titol = re.search(r'class="linkTitle trackTitle"[^>]*title="([^"]+)"', bloc)
        if not m_titol:
            # provar amb el títol de l'enllaç number/imageWrapper del bloc anterior
            prev = blocs[i-1][-1500:] if i-1 >= 0 else ''
            m_titol = re.search(r'class="linkTitle trackTitle"[^>]*title="([^"]+)"', prev)
            if m_titol:
                bloc = prev + bloc
        titol = html_unescape(m_titol.group(1)) if m_titol else None

        # Portada: <img src="/track_image/UUID/...">
        m_img = re.search(r'src="(/track_image/[\w-]+/\d+x\d+/\d+)"', bloc)
        if not m_img:
            m_img = re.search(r'/track_image/' + re.escape(uuid) + r'/\d+x\d+/\d+', bloc)
            cover_url = f"https://hardstyle.com{m_img.group(0)}" if m_img else None
        else:
            cover_url = f"https://hardstyle.com{m_img.group(1)}"

        # Artista: primer enllaç a /en/artists/ o /en/music?artist= amb title
        m_art = re.search(r'href="/en/(?:artists/[\w-]+|music\?artist=[^"]+)"[^>]*title="([^"]+)"', bloc)
        artista = html_unescape(m_art.group(1)) if m_art else ''

        if titol:
            vistos.add(uuid)
            tracks.append({
                'pos': pos, 'nom': titol, 'artista': artista, 'cover_url': cover_url,
                'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
            })
            pos += 1

    return tracks, setmana_text

if GENERE == 'hardstyle':
    tracks, setmana_text = scrape_hardstyle()
else:
    try:
        tracks, setmana_text = scrape_electronica_tidal()
        if not tracks:
            raise Exception("Tidal no ha retornat tracks")
    except Exception as e:
        print(f"ERROR amb Tidal ({e}), fent servir dance-charts.de com a reserva")
        tracks, setmana_text = scrape_electronica_dancecharts()

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

print(f"Setmana: {setmana_text}")
print(f"\nTracks trobats ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")

data = {
    'genere': GENERE,
    'setmana_text': setmana_text,
    'tracks': tracks
}
with open('chart2_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\nchart2_data.json escrit!")
