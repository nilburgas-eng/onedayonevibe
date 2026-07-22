import os, json, re
import requests

GENERE = os.environ.get('GENERE', 'electronica')

def scrape_electronica():
    url = "https://www.electricfm.com/music/weekly-top-20-chart"
    print(f"Scraping electronica: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text

    setmana_text = ""
    m = re.search(r'Week of ([A-Z][a-z]+ \d+, \d{4})', html)
    if m:
        setmana_text = f"WEEK OF {m.group(1).upper()}"

    net = re.sub(r'<[^>]+>', '\n', html)
    net = re.sub(r'&amp;', '&', net)
    net = re.sub(r'&#039;|&#39;', "'", net)
    net = re.sub(r'&quot;', '"', net)
    linies = [l.strip() for l in net.split('\n')]
    linies = [l for l in linies if l]

    tracks = []
    vistos = set()
    i = 0
    while i < len(linies) and len(tracks) < 10:
        m_pos = re.match(r'^#(\d+)$', linies[i])
        if m_pos:
            pos_num = int(m_pos.group(1))
            resta = [l for l in linies[i+1:i+6] if l and not re.match(r'^#\d+$', l)]
            if len(resta) >= 2:
                nom = resta[0]
                artista = resta[1]
                key = (nom.lower(), artista.lower())
                if key not in vistos and pos_num <= 10:
                    vistos.add(key)
                    tracks.append({
                        'pos': pos_num, 'nom': nom, 'artista': artista, 'cover_url': None,
                        'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
                    })
        i += 1
    tracks.sort(key=lambda t: t['pos'])
    return tracks, setmana_text

def scrape_hardstyle():
    url = "https://hardstyle.com/en/charts?genre=hardstyle"
    print(f"Scraping hardstyle: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text

    # === DEBUG ===
    print("=== DEBUG: mida HTML:", len(html))
    idx = html.find('track_image')
    print("=== Primera aparicio track_image a la posicio:", idx)
    if idx > 0:
        print("=== Fragment al voltant de track_image:")
        print(html[idx-300:idx+700])
    idx2 = html.find('/en/tracks/')
    print("=== Primera aparicio /en/tracks/ a la posicio:", idx2)
    if idx2 > 0:
        print("=== Fragment al voltant de /en/tracks/:")
        print(html[idx2-200:idx2+500])
    print("=== FI DEBUG ===")

    setmana_text = "HARDSTYLE TOP 10"

    tracks = []
    blocs = re.split(r'track_image/', html)
    pos = 1
    for i in range(1, len(blocs)):
        if pos > 10:
            break
        bloc = blocs[i][:2500]
        m_img = re.match(r'([\w-]+/\d+x\d+/\d+)', bloc)
        cover_url = f"https://hardstyle.com/track_image/{m_img.group(1)}" if m_img else None
        m = re.search(r'\]\(https://hardstyle\.com/en/tracks/[\w-]+/[\w-]+\s+"([^"]+)"\)', bloc)
        titol = m.group(1) if m else None
        m_art = re.search(r'\]\(https://hardstyle\.com/en/(?:artists/[\w-]+|music\?artist=[^\)]+)\s+"([^"]+)"\)', bloc)
        artista = m_art.group(1) if m_art else ''
        if titol:
            tracks.append({
                'pos': pos, 'nom': titol, 'artista': artista, 'cover_url': cover_url,
                'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
            })
            pos += 1
    return tracks, setmana_text

if GENERE == 'hardstyle':
    tracks, setmana_text = scrape_hardstyle()
else:
    tracks, setmana_text = scrape_electronica()

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
