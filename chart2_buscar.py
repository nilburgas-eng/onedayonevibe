import os, json, re
import requests

def scrape_chart():
    url = "https://www.electricfm.com/music/weekly-top-20-chart"
    print(f"Scraping: {url}")
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
                        'pos': pos_num, 'nom': nom, 'artista': artista,
                        'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
                    })
        i += 1

    tracks.sort(key=lambda t: t['pos'])
    return tracks, setmana_text

tracks, setmana_text = scrape_chart()

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

print(f"Setmana: {setmana_text}")
print(f"\nTracks trobats ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")

data = {
    'setmana_text': setmana_text,
    'tracks': tracks
}
with open('chart2_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\nchart2_data.json escrit!")
