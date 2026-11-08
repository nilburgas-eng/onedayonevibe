import os, re, time, json, html as htmllib
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests

# PROVA EXPLORATORIA (no genera cap video ni publica res).
# Llegeix poques pagines de hdrr.info i mostra al log que hi veu, per decidir com fer el format
# "Daily Hardstyle Releases". Total de peticions: unes 12, amb pausa entre elles.

BASE = os.environ.get('HDRR_BASE', 'https://www.hdrr.info').rstrip('/')
LLISTA = '/new-hardstyle-releases'
PAUSA = 2.0
UA = "onedayonevibe-prova/0.1 (lectura puntual i lenta; contacte via GitHub nilburgas-eng)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en"}

RE_DATA = re.compile(r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d\d)\b')
RE_TRACK = re.compile(r'href=["\'](/tracks/[^"\'#? ]+)["\']')
RE_ISRC = re.compile(r'\b([A-Z]{2}[A-Z0-9]{3}\d{7})\b')
RE_POP = re.compile(r'(\d{1,3})\s*/\s*100')
RE_SPOTIFY = re.compile(r'https?://open\.spotify\.com/(?:intl-[a-z]+/)?track/([A-Za-z0-9]+)')


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    time.sleep(PAUSA)
    return r


def text_pla(h):
    h = re.sub(r'(?is)<(script|style).*?</\1>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', htmllib.unescape(h)).strip()


print(f"Base: {BASE}\n")

# ---------- 1. robots.txt ----------
print("=== 1. robots.txt ===")
try:
    r = get(BASE + '/robots.txt')
    print(f"Estat: {r.status_code}")
    print(r.text[:1500] if r.status_code == 200 else '(no disponible)')
    if r.status_code == 200:
        rp = RobotFileParser()
        rp.parse(r.text.splitlines())
        for ruta in (LLISTA, '/tracks/spark-inside'):
            print(f"Permet '{ruta}' a un bot generic? {rp.can_fetch('*', BASE + ruta)}")
        print(f"Crawl-delay: {rp.crawl_delay('*')}")
except Exception as e:
    print(f"ERROR: {e}")

# ---------- 2. paginacio de la llista ----------
print("\n=== 2. Llista de llancaments (paginacio) ===")
pagines = {}
for p in (1, 2, 9):
    url = f"{BASE}{LLISTA}?page={p}"
    try:
        r = get(url)
        slugs = []
        for s in RE_TRACK.findall(r.text):
            if s not in slugs:
                slugs.append(s)
        dates = RE_DATA.findall(text_pla(r.text))
        dist = {}
        for d in dates:
            dist[d] = dist.get(d, 0) + 1
        pagines[p] = slugs
        print(f"page={p}: estat {r.status_code}, URL final {r.url}")
        print(f"   enllacos a temes: {len(slugs)} | primers: {slugs[:3]}")
        print(f"   dates a la pagina: {dist}")
    except Exception as e:
        print(f"page={p}: ERROR {e}")
if 1 in pagines and 9 in pagines:
    print(f"\nLa pagina 1 i la 9 tenen els mateixos temes? {pagines[1] == pagines[9]}")
    if pagines[1] == pagines[9]:
        print("   -> el parametre ?page= no canvia el contingut (potser va per JavaScript o a una altra URL)")

# ---------- 3. detall dels primers temes ----------
print("\n=== 3. Detall de temes (de la pagina 1) ===")
slugs = pagines.get(1, [])[:5]
if not slugs:
    print("No hi ha cap tema per llegir. Mostro el principi del HTML de la pagina 1 per veure l'estructura:")
    try:
        r = get(f"{BASE}{LLISTA}?page=1")
        print(r.text[:2500])
    except Exception as e:
        print(f"ERROR: {e}")
resultats = []
for s in slugs:
    url = urljoin(BASE + '/', s.lstrip('/'))
    try:
        r = get(url)
        h = r.text
        txt = text_pla(h)
        titol = ''
        m = re.search(r'(?is)<h1[^>]*>(.*?)</h1>', h)
        if m:
            titol = text_pla(m.group(1))
        isrc = RE_ISRC.search(txt)
        pop = None
        mp = re.search(r'(?i)popularity[^0-9]{0,40}(\d{1,3})\s*/\s*100', txt) or RE_POP.search(txt)
        if mp:
            pop = int(mp.group(1))
        sp = RE_SPOTIFY.search(h)
        data = RE_DATA.search(txt)
        genere = ''
        mg = re.search(r'(?i)genre[:\s]+([A-Za-z ,&\-]{3,60}?)(?:\s{2,}|Label|Released|Length|ISRC|$)', txt)
        if mg:
            genere = mg.group(1).strip()
        playlists = sorted(set(re.findall(r'(?i)(Hardstyle (?:Release Radar|Top 100))', txt)))
        item = {'slug': s, 'titol': titol, 'data': data.group(1) if data else '', 'genere': genere,
                'isrc': isrc.group(1) if isrc else '', 'popularitat': pop,
                'spotify_id': sp.group(1) if sp else '', 'playlists_hdrr': playlists}
        resultats.append(item)
        print(json.dumps(item, ensure_ascii=False))
    except Exception as e:
        print(f"{s}: ERROR {e}")

print(f"\nResum: {len(resultats)} temes llegits, "
      f"{sum(1 for x in resultats if x['spotify_id'])} amb enllac de Spotify, "
      f"{sum(1 for x in resultats if x['popularitat'] is not None)} amb popularitat, "
      f"{sum(1 for x in resultats if x['isrc'])} amb ISRC")
