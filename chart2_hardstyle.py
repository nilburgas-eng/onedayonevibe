import re
import requests

def scrape_hardstyle():
    url = "https://hardstyle.com/en/charts?genre=hardstyle"
    print(f"Scraping: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text

    tracks = []
    # Cada cançó té un bloc amb track_image i enllaç /tracks/UUID/slug
    # Patró: track_image URL ... [Titol](/tracks/UUID/slug) ... [Artista](...)
    # Busquem els blocs per posició (01, 02...) fins a 10

    # Dividim per les imatges de track (marca l'inici de cada cançó)
    blocs = re.split(r'track_image/', html)

    pos = 1
    for i in range(1, len(blocs)):
        if pos > 10:
            break
        bloc = blocs[i][:2000]  # només el principi del bloc

        # URL de la portada: reconstruïm
        m_img = re.match(r'([\w-]+/\d+x\d+/\d+)', bloc)
        cover_url = f"https://hardstyle.com/track_image/{m_img.group(1)}" if m_img else None

        # Títol: primer enllaç a /tracks/ després de la imatge amb text
        m_titol = re.search(r'/tracks/[\w-]+/[\w-]+\s+"([^"]+)"\)\s*\[([^\]]+)\]', bloc)
        # Busquem el patró [Titol](.../slug "Titol")[Versio]
        m = re.search(r'\]\(https://hardstyle\.com/en/tracks/[\w-]+/[\w-]+\s+"([^"]+)"\)', bloc)
        titol = m.group(1) if m else None

        # Artista: primer enllaç a /artists/ o /music?artist= amb text
        m_art = re.search(r'\]\(https://hardstyle\.com/en/(?:artists/[\w-]+|music\?artist=[^\)]+)\s+"([^"]+)"\)', bloc)
        artista = m_art.group(1) if m_art else ''

        if titol:
            tracks.append({
                'pos': pos,
                'nom': titol,
                'artista': artista,
                'cover_url': cover_url,
                'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
            })
            pos += 1

    return tracks

if __name__ == '__main__':
    tracks = scrape_hardstyle()
    print(f"\nTracks ({len(tracks)}):")
    for t in tracks:
        print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")
        print(f"       cover: {t['cover_url']}")
