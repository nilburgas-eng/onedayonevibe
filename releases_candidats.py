import os, re, json, time, random, unicodedata, html as htmllib
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import requests

# ODOV Daily Hardstyle Releases - pas 1: proposar candidats del dia.
# Llegeix hdrr.info (llista de nous llancaments + Top 100), filtra, puntua i escriu releases_candidats.json.
# No publica res ni toca TikTok ni Spotify. Total de peticions: unes 10-15, amb pausa entre elles.

BASE = os.environ.get('HDRR_BASE', 'https://www.hdrr.info').rstrip('/')
LLISTA = '/new-hardstyle-releases'
TOP100 = '/hardstyle-top-100'
PAUSA = float(os.environ.get('HDRR_PAUSA', '2.0'))
UA = "onedayonevibe/0.2 (lectura lenta, unes poques pagines al dia; contacte via GitHub nilburgas-eng)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en"}

OUT_PATH = 'releases_candidats.json'
HIST_PATH = 'releases_historial.json'     # el web app hi anota els temes ja publicats (opcional)
CHART_PATH = 'chart_historial.json'       # el que ja genera el chart setmanal

# --- pesos (primera proposta, a revisar amb dades reals) ---
PUNTS_TOP100 = 50      # millor posicio d'un artista al Top 100 de HDRR (#1 = 50, #100 = ~0)
PUNTS_CHART = 30       # millor posicio d'un artista al teu chart setmanal (#1 = 30)
CHART_MAX_POS = 15
PENAL_VERSIO = 20      # radio edit / extended / speed up / remix edit...
N_CANDIDATS = 3
DIES_SENSE_REPETIR = 7
MAX_PAGINES = 10

GENERES_OK = ('hardstyle', 'euphoric', 'rawstyle')
GENERES_NO = ('uptempo', 'hardcore', 'frenchcore')
RE_VERSIO = re.compile(r'(?i)\b(radio edit|radio mix|extended|speed(?:ed)?[ -]?up|sped up|slowed|instrumental|remix edit|live edit|edit|remix|vip|reverb|bootleg|mashup)\b')

MESOS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
RE_DATA = re.compile(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d\d)\b')
RE_IMG = re.compile(r'<img\b[^>]*>', re.I)
RE_ALT = re.compile(r'\balt\s*=\s*("([^"]*)"|\'([^\']*)\')', re.I)
RE_SRC = re.compile(r'\bsrc\s*=\s*("([^"]*)"|\'([^\']*)\')', re.I)
RE_TRACKLINK = re.compile(r'href\s*=\s*["\'](?:https?://[^/"\']+)?(/tracks/[^"\'#? ]+)["\']', re.I)
RE_ISRC = re.compile(r'\b([A-Z]{2}[A-Z0-9]{3}\d{7})\b')
RE_SPOTIFY = re.compile(r'https?://open\.spotify\.com/(?:intl-[a-z]+/)?track/([A-Za-z0-9]+)')

AVISOS = []


def avis(msg):
    print('AVIS:', msg)
    AVISOS.append(msg)


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    time.sleep(PAUSA)
    return r


def text_pla(h):
    h = re.sub(r'(?is)<(script|style).*?</\1>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', htmllib.unescape(h)).strip()


def norm(s):
    s = unicodedata.normalize('NFKD', htmllib.unescape(str(s)))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('&', ' ')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', norm(s)).strip('-')


def parse_alt(alt):
    """'Titol by A, B - Genere cover art' -> (titol, [artistes], genere) o None"""
    a = htmllib.unescape(htmllib.unescape(alt)).strip()
    m = re.match(r'(?is)^(.*?)\s+cover art\s*$', a)
    if not m:
        return None
    a = m.group(1)
    if ' - ' not in a or ' by ' not in a:
        return None
    resta, genere = a.rsplit(' - ', 1)
    titol, artistes = resta.rsplit(' by ', 1)
    llista = [x.strip() for x in artistes.split(', ') if x.strip()]
    return titol.strip(), llista, genere.strip()


def parse_data(txt):
    m = RE_DATA.search(txt)
    if not m:
        return None
    return datetime(int(m.group(3)), MESOS[m.group(2).lower()], int(m.group(1))).date()


def parse_pagina(h, vigilar_enllacos=True):
    """Retorna llista d'entrades {titol, artistes, genere, portada, slug, data} en ordre de pagina."""
    pos = []
    for m in RE_IMG.finditer(h):
        tag = m.group(0)
        ma = RE_ALT.search(tag)
        if not ma:
            continue
        p = parse_alt(ma.group(2) or ma.group(3) or '')
        if not p:
            continue
        ms = RE_SRC.search(tag)
        src = (ms.group(2) or ms.group(3)) if ms else ''
        pos.append((m.start(), m.end(), p, src))
    ent = []
    for i, (a, b, p, src) in enumerate(pos):
        fi = pos[i + 1][0] if i + 1 < len(pos) else len(h)
        seg = h[b:fi]
        prev_seg = h[pos[i - 1][1]:a] if i > 0 else h[max(0, a - 1500):a]
        la = RE_TRACKLINK.findall(seg)
        lb = RE_TRACKLINK.findall(prev_seg)
        ent.append({'titol': p[0], 'artistes': p[1], 'genere': p[2], 'portada': src,
                    'data': parse_data(text_pla(seg)), '_A': la[0] if la else '', '_B': lb[-1] if lb else ''})
    # decidir si l'enllac del tema va despres (A) o abans (B) de la imatge, segons quin s'assembla mes al titol
    def qualitat(clau):
        ok = 0
        for e in ent:
            s = e[clau].replace('/tracks/', '')
            s = re.sub(r'-\d+$', '', s)
            t = slugify(e['titol'])
            if s and SequenceMatcher(None, s, t).ratio() >= 0.6:
                ok += 1
        return ok
    qa, qb = qualitat('_A'), qualitat('_B')
    clau = '_A' if qa >= qb else '_B'
    if vigilar_enllacos and ent and max(qa, qb) < len(ent) * 0.6:
        avis(f"L'enllac dels temes no quadra del tot amb els titols ({max(qa, qb)}/{len(ent)}); reviso al log")
    for e in ent:
        e['slug'] = e[clau]
        del e['_A'], e['_B']
    return ent


def llegir_llista(avui):
    totes = []
    for p in range(1, MAX_PAGINES + 1):
        r = get(f"{BASE}{LLISTA}?page={p}")
        if r.status_code != 200:
            avis(f"Llista pagina {p}: estat {r.status_code}")
            break
        ent = parse_pagina(r.text)
        dates = [e['data'] for e in ent if e['data']]
        print(f"Llista p{p}: {len(ent)} temes, dates {min(dates) if dates else '-'}..{max(dates) if dates else '-'}")
        if not ent:
            avis(f"Llista pagina {p}: no he trobat cap tema (potser ha canviat el format de HDRR)")
            break
        totes += ent
        if dates and max(dates) < avui:
            break
    return totes


def llegir_top100():
    r = get(BASE + TOP100)
    if r.status_code != 200:
        avis(f"Top 100: estat {r.status_code}")
        return {}
    ent = parse_pagina(r.text, vigilar_enllacos=False)
    print(f"Top 100: {len(ent)} temes llegits")
    if len(ent) < 50:
        avis(f"Top 100: nomes he llegit {len(ent)} temes, la puntuacio per artistes sera parcial")
    mapa = {}
    for i, e in enumerate(ent, 1):
        for a in e['artistes']:
            k = norm(a)
            if k and (k not in mapa or i < mapa[k][0]):
                mapa[k] = (i, a)
    return mapa


def llegir_chart():
    """Retorna (text normalitzat per posicio) del darrer snapshot de hardstyle del chart propi."""
    try:
        with open(CHART_PATH, encoding='utf-8') as f:
            h = json.load(f)
        snaps = [s for s in h.get('snapshots', []) if s.get('genere') == 'hardstyle']
        if not snaps:
            return []
        snaps.sort(key=lambda s: s.get('data', ''))
        return [(int(t.get('pos', 99)), norm(t.get('artista', ''))) for t in snaps[-1].get('tracks', [])]
    except Exception as e:
        print('Chart propi no disponible:', e)
        return []


def llegir_historial():
    try:
        with open(HIST_PATH, encoding='utf-8') as f:
            return json.load(f).get('picks', [])
    except Exception:
        return []


def genere_valid(g):
    gl = g.lower()
    return any(x in gl for x in GENERES_OK) and not any(x in gl for x in GENERES_NO)


def base_titol(t):
    t = re.sub(r'\s*[-\(\[].*$', '', t)
    return norm(t)


def puntuar(e, top100, chart):
    punts, motius = 0.0, []
    millor = None
    for a in e['artistes']:
        v = top100.get(norm(a))
        if v and (millor is None or v[0] < millor[0]):
            millor = (v[0], a)
    if millor:
        p = PUNTS_TOP100 * (101 - millor[0]) / 100
        punts += p
        motius.append(f"{millor[1]}: #{millor[0]} al Top 100 de HDRR (+{p:.1f})")
    mc = None
    for a in e['artistes']:
        na = norm(a)
        if len(na) < 3:
            continue
        for pos, txt in chart:
            if f" {na} " in f" {txt} " and pos <= CHART_MAX_POS and (mc is None or pos < mc[0]):
                mc = (pos, a)
    if mc:
        p = PUNTS_CHART * (CHART_MAX_POS + 1 - mc[0]) / CHART_MAX_POS
        punts += p
        motius.append(f"{mc[1]}: #{mc[0]} al teu chart (+{p:.1f})")
    if e.get('versio'):
        punts -= PENAL_VERSIO
        motius.append(f"versio alternativa (-{PENAL_VERSIO})")
    return round(punts, 1), motius


def enriquir(e):
    """Pagina del tema: enllac de Spotify, popularitat, ISRC i portada gran."""
    info = {'spotify_id': '', 'popularitat': None, 'isrc': ''}
    url = f"{BASE}{e['slug']}" if e['slug'] else ''
    if not url:
        return info
    try:
        r = get(url)
        txt = text_pla(r.text)
        m = RE_SPOTIFY.search(r.text)
        if m:
            info['spotify_id'] = m.group(1)
        mp = re.search(r'(?i)popularity[^0-9]{0,40}(\d{1,3})\s*/\s*100', txt) or re.search(r'(\d{1,3})\s*/\s*100', txt)
        if mp:
            info['popularitat'] = int(mp.group(1))
        mi = RE_ISRC.search(txt)
        if mi:
            info['isrc'] = mi.group(1)
    except Exception as ex:
        avis(f"No he pogut llegir {url}: {ex}")
    return info


def portada_gran(src):
    """Intenta la portada de 480 px; si no existeix, torna la que hi ha."""
    if not src:
        return ''
    url = src if src.startswith('http') else BASE + src
    gran = re.sub(r'/covers/\d+/', '/covers/480/', url)
    if gran != url:
        try:
            r = requests.get(gran, headers=HEADERS, timeout=20)
            time.sleep(PAUSA)
            if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
                return gran
        except Exception:
            pass
    return url


# ---------------------------------------------------------------- principal
ARA = datetime.now(timezone.utc)
data_env = os.environ.get('DATA', '').strip()
if data_env:
    avui = datetime.strptime(data_env, '%Y-%m-%d').date()
else:
    avui = (ARA + timedelta(hours=1)).date()   # Europa/Madrid aprox. (UTC+1/+2)
    if ARA.hour >= 22:
        avui = (ARA + timedelta(hours=2)).date()
print(f"Data objectiu: {avui}\n")

totes = llegir_llista(avui)
del_dia = [e for e in totes if e['data'] == avui]
print(f"Temes d'avui a la llista: {len(del_dia)} (de {len(totes)} llegits)")
if not del_dia:
    avis("Cap llancament d'aquesta data a HDRR (potser encara no s'han afegit)")

filtrats = [e for e in del_dia if genere_valid(e['genere'])]
print(f"Despres del filtre de genere: {len(filtrats)}")

# versions
comptes = {}
for e in filtrats:
    comptes[base_titol(e['titol'])] = comptes.get(base_titol(e['titol']), 0) + 1
for e in filtrats:
    e['versio'] = bool(RE_VERSIO.search(e['titol']))
final = []
for e in filtrats:
    # si hi ha una altra versio del mateix titol el mateix dia, es descarta la versio alternativa
    if e['versio'] and comptes[base_titol(e['titol'])] > 1:
        continue
    final.append(e)

# historial: no repetir artista principal ni tema
hist = llegir_historial()
limit = avui - timedelta(days=DIES_SENSE_REPETIR)
recents, ja_fets = set(), set()
for p in hist:
    try:
        d = datetime.strptime(p.get('data', ''), '%Y-%m-%d').date()
    except Exception:
        continue
    if d >= limit and p.get('artistes'):
        recents.add(norm(p['artistes'][0]))
    if p.get('spotify_id'):
        ja_fets.add(p['spotify_id'])
final = [e for e in final if not (e['artistes'] and norm(e['artistes'][0]) in recents)]

top100 = llegir_top100()
chart = llegir_chart()
print(f"Artistes al Top 100: {len(top100)} | temes al chart propi: {len(chart)}")

for e in final:
    e['punts'], e['motius'] = puntuar(e, top100, chart)
final.sort(key=lambda e: (-e['punts'], e['titol'].lower()))

print("\n--- Rànquing ---")
for i, e in enumerate(final[:15], 1):
    print(f"{i:2d}. {e['punts']:5.1f}  {e['titol']} | {', '.join(e['artistes'])} | {e['genere']}  {'; '.join(e['motius'])}")

cands = final[:N_CANDIDATS]
resta = final[N_CANDIDATS:]
comodi = None
rnd = random.Random(str(avui))
pool = [e for e in resta if not e.get('versio')]
if pool:
    comodi = rnd.choice(pool)
    comodi['comodi'] = True

sortida = []
for e in cands + ([comodi] if comodi else []):
    info = enriquir(e)
    if info['spotify_id'] and info['spotify_id'] in ja_fets:
        avis(f"{e['titol']} ja s'havia publicat")
    if not info['spotify_id']:
        avis(f"{e['titol']}: no he trobat l'enllac de Spotify")
    sortida.append({
        'titol': e['titol'], 'artistes': e['artistes'], 'genere': e['genere'], 'data': str(e['data']),
        'punts': e['punts'], 'motius': e['motius'], 'versio': bool(e.get('versio')), 'comodi': bool(e.get('comodi')),
        'hdrr_url': f"{BASE}{e['slug']}" if e['slug'] else '',
        'spotify_id': info['spotify_id'],
        'spotify_url': f"https://open.spotify.com/track/{info['spotify_id']}" if info['spotify_id'] else '',
        'popularitat_hdrr': info['popularitat'], 'isrc': info['isrc'],
        'portada': portada_gran(e['portada']),
    })

res = {
    'data': str(avui), 'generat': ARA.isoformat(timespec='seconds'), 'font': 'hdrr.info',
    'candidats': sortida,
    'resta': [{'titol': e['titol'], 'artistes': e['artistes'], 'genere': e['genere'], 'punts': e['punts']} for e in resta],
    'estadistiques': {'llegits': len(totes), 'del_dia': len(del_dia), 'despres_filtre': len(final),
                      'artistes_top100': len(top100), 'temes_chart_propi': len(chart)},
    'avisos': AVISOS,
}
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print(f"\nEscrit {OUT_PATH}: {len(sortida)} candidats")
if not sortida:
    print("Avui no hi ha cap candidat: no cal publicar.")
