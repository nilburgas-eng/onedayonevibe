import os, sys, re, json, time, unicodedata, html as htmllib
from datetime import datetime, timedelta, timezone
import requests

# ODOV Daily Hardstyle Releases - pas 2: mantenir la playlist de Spotify sense intervencio.
#  - afegeix els millors temes nous de cada dia (maxim MAX_PER_DIA), els millors a dalt
#  - no repeteix temes ni versions del mateix tema (radio edit, extended...)
#  - treu nomes els temes de mes d'un any
# No depen de TikTok: s'executa tant si publiques com si no.

ACCOUNTS = os.environ.get('SPOTIFY_ACCOUNTS', 'https://accounts.spotify.com').rstrip('/')
API = os.environ.get('SPOTIFY_API', 'https://api.spotify.com/v1').rstrip('/')
CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '').strip()
REFRESH = os.environ.get('SPOTIFY_REFRESH_TOKEN', '').strip()
PLAYLIST = os.environ.get('SPOTIFY_PLAYLIST_ID', '').strip()

CANDIDATS_PATH = 'releases_candidats.json'
LOG_PATH = 'releases_playlist_log.json'

MAX_PER_DIA = 5          # maxim de temes per data de sortida que entren a la playlist
DIES_FINESTRA = 365       # es treuen els temes de mes d'un any
MAX_AFEGIR_EXEC = 300     # seguretat: mai afegir mes d'aixo en una execucio
MAX_ELIMINAR_EXEC = 100   # seguretat: mai treure mes d'aixo d'un cop
AFEGIR_VERSIO_SOLA = True # una versio (extended, radio edit...) s'afegeix si es l'unica del tema
PAUSA = 0.4

if not (CLIENT_ID and REFRESH and PLAYLIST):
    print("Spotify encara no esta configurat (falten SPOTIFY_CLIENT_ID, SPOTIFY_REFRESH_TOKEN o SPOTIFY_PLAYLIST_ID). No toco la playlist.")
    sys.exit(0)

ARA = datetime.now(timezone.utc)
RE_VERSIO = re.compile(r'(?i)\b(radio edit|radio mix|extended|speed(?:ed)?[ -]?up|sped up|slowed|instrumental|remix edit|live edit|edit|remix|vip|reverb|bootleg|mashup)\b')


def norm(s):
    s = unicodedata.normalize('NFKD', htmllib.unescape(str(s)))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('&', ' ')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def base_titol(t):
    return norm(re.sub(r'\s*[-\(\[].*$', '', t))


def token():
    r = requests.post(f"{ACCOUNTS}/api/token", data={
        'grant_type': 'refresh_token', 'refresh_token': REFRESH, 'client_id': CLIENT_ID}, timeout=25)
    if r.status_code != 200:
        print(f"ERROR obtenint el token de Spotify: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    return r.json()['access_token']


H = {}


def api(method, path, **kw):
    r = requests.request(method, f"{API}{path}", headers=H, timeout=30, **kw)
    time.sleep(PAUSA)
    return r


def llegir_playlist():
    """Retorna llista (de dalt a baix) de {uri, id, added_at, nom, artista1} o None si falla."""
    out, offset = [], 0
    while True:
        r = api('GET', f"/playlists/{PLAYLIST}/items", params={'limit': 50, 'offset': offset})
        if r.status_code != 200:
            print(f"ERROR llegint la playlist: {r.status_code} {r.text[:300]}")
            return None
        j = r.json()
        for it in j.get('items', []):
            obj = it.get('item') or it.get('track') or {}
            uri = obj.get('uri') or ''
            if uri.startswith('spotify:track:'):
                arts = [a.get('name', '') for a in (obj.get('artists') or [])]
                out.append({'uri': uri, 'id': uri.split(':')[-1], 'added_at': it.get('added_at') or '',
                            'nom': obj.get('name', ''), 'artista1': arts[0] if arts else ''})
        if not j.get('next'):
            break
        offset += 50
    return out


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


def eliminar(uris):
    ok = 0
    for i in range(0, len(uris), 50):
        lot = uris[i:i + 50]
        for camp in ('items', 'tracks'):
            r = api('DELETE', f"/playlists/{PLAYLIST}/items", json={camp: [{'uri': u} for u in lot]})
            if r.status_code == 200:
                ok += len(lot)
                break
            print(f"   DELETE amb '{camp}': {r.status_code} {r.text[:200]}")
    return ok


def afegir_a_dalt(uris, total_abans):
    """Afegeix els temes al principi de la playlist, en l'ordre donat (el primer queda el primer)."""
    # en blocs de 100, de l'ultim al primer, perque el primer bloc acabi a dalt
    blocs = [uris[i:i + 100] for i in range(0, len(uris), 100)]
    n_ok = 0
    for bloc in reversed(blocs):
        r = api('POST', f"/playlists/{PLAYLIST}/items", json={'uris': bloc, 'position': 0})
        if r.status_code in (200, 201):
            n_ok += len(bloc)
            total_abans += len(bloc)
            continue
        print(f"   POST amb posicio 0: {r.status_code} {r.text[:200]}")
        # alternativa: afegir al final i moure'ls a dalt
        r = api('POST', f"/playlists/{PLAYLIST}/items", json={'uris': bloc})
        if r.status_code not in (200, 201):
            print(f"   POST sense posicio: {r.status_code} {r.text[:200]}")
            continue
        r2 = api('PUT', f"/playlists/{PLAYLIST}/items", json={'range_start': total_abans, 'insert_before': 0, 'range_length': len(bloc)})
        if r2.status_code == 200:
            n_ok += len(bloc)
            total_abans += len(bloc)
        else:
            print(f"   AVIS: afegits al final i NO he pogut moure'ls a dalt: {r2.status_code} {r2.text[:200]}")
            n_ok += len(bloc)
            total_abans += len(bloc)
    return n_ok


H['Authorization'] = f"Bearer {token()}"

actual = llegir_playlist()
if actual is None:
    print("No continuo sense poder llegir la playlist.")
    sys.exit(1)
print(f"La playlist te {len(actual)} temes")
existents = {x['id'] for x in actual}
existents_titols = {(base_titol(x['nom']), norm(x['artista1'])) for x in actual if x['nom']}

# --- mode "afegir un tema concret" (el fa servir el generador de carrusels) ---
forcat = os.environ.get('AFEGIR_ID', '').strip()
if forcat:
    if forcat in existents:
        print("El tema ja es a la playlist: no cal afegir-lo.")
        n_forcat = 0
    else:
        n_forcat = afegir_a_dalt([f"spotify:track:{forcat}"], len(actual))
        print(f"Tema afegit a dalt de la playlist: {n_forcat}")
    try:
        with open(LOG_PATH, encoding='utf-8') as f:
            log = json.load(f)
    except Exception:
        log = {'dies': []}
    if n_forcat:
        log['dies'].append({'data': ARA.date().isoformat(), 'executat': ARA.isoformat(timespec='seconds'),
                            'afegits': [{'titol': os.environ.get('AFEGIR_TITOL', ''), 'spotify_id': forcat, 'manual': True}], 'eliminats': 0})
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=1)
    sys.exit(0)

# --- 1. finestra d'un any ---
limit = ARA - timedelta(days=DIES_FINESTRA)
vells = [x for x in actual if x['added_at'] and (parse_dt(x['added_at']) or ARA) < limit]
eliminats = 0
if vells:
    if len(vells) > MAX_ELIMINAR_EXEC:
        print(f"AVIS: {len(vells)} temes per treure; per seguretat nomes en trec {MAX_ELIMINAR_EXEC}")
        vells = vells[:MAX_ELIMINAR_EXEC]
    eliminats = eliminar([x['uri'] for x in vells])
    print(f"Eliminats {eliminats} temes de mes de {DIES_FINESTRA} dies")
else:
    print(f"Cap tema supera els {DIES_FINESTRA} dies")

# --- 2. temes nous ---
try:
    with open(CANDIDATS_PATH, encoding='utf-8') as f:
        cand = json.load(f)
except Exception as e:
    print(f"No puc llegir {CANDIDATS_PATH}: {e}")
    cand = {}

# quants temes de cada data ja hi son a la playlist (per no passar del maxim si hi ha dues execucions al dia)
from collections import Counter
per_data = Counter(c.get('data') for c in cand.get('tots', []) if c.get('spotify_id') in existents)
triats, vistos = [], set()
for c in cand.get('tots', []):          # ja ve ordenat: dia mes recent primer, i dins del dia, millor puntuacio primer
    sid = c.get('spotify_id')
    if not sid or sid in vistos:
        continue
    if c.get('versio') and not AFEGIR_VERSIO_SOLA:
        continue
    if sid in existents:
        continue
    clau = (base_titol(c['titol']), norm(c['artistes'][0]) if c.get('artistes') else '')
    if clau in existents_titols:
        print(f"   ja hi ha una versio d'aquest tema: {c['titol']}")
        continue
    if per_data[c.get('data')] >= MAX_PER_DIA:
        continue
    per_data[c.get('data')] += 1
    vistos.add(sid)
    existents_titols.add(clau)
    triats.append(c)
if len(triats) > MAX_AFEGIR_EXEC:
    print(f"AVIS: {len(triats)} temes nous; per seguretat n'afegeixo {MAX_AFEGIR_EXEC}")
    triats = triats[:MAX_AFEGIR_EXEC]

afegits = []
if triats:
    uris = [f"spotify:track:{c['spotify_id']}" for c in triats]
    n = afegir_a_dalt(uris, len(actual))
    if n:
        afegits = [{'titol': c['titol'], 'artistes': c['artistes'], 'spotify_id': c['spotify_id'], 'data': c.get('data'), 'punts': c.get('punts')} for c in triats]
        for c in triats[:25]:
            print(f"   AFEGIT: {c['titol']} - {', '.join(c['artistes'])} ({c.get('data')}, {c.get('punts')} punts)")
        if len(triats) > 25:
            print(f"   ... i {len(triats) - 25} mes")
        # comprovacio: els nous han d'estar a dalt de tot
        despres = llegir_playlist()
        if despres:
            dalt = [x['id'] for x in despres[:len(triats)]]
            esperats = {c['spotify_id'] for c in triats}
            if set(dalt) == esperats:
                print("Comprovat: els temes nous son a dalt de la playlist.")
            else:
                print("AVIS: els temes nous NO apareixen a dalt de tot; cal revisar l'ordre de la playlist.")
    else:
        print("ERROR afegint temes a la playlist")
else:
    print("Avui no hi ha cap tema nou per afegir")

# --- 3. registre ---
try:
    with open(LOG_PATH, encoding='utf-8') as f:
        log = json.load(f)
except Exception:
    log = {'dies': []}
log['dies'].append({'data': cand.get('data', ARA.date().isoformat()), 'executat': ARA.isoformat(timespec='seconds'),
                    'afegits': afegits, 'eliminats': eliminats})
log['dies'] = log['dies'][-120:]
with open(LOG_PATH, 'w', encoding='utf-8') as f:
    json.dump(log, f, ensure_ascii=False, indent=1)
print(f"Resultat: +{len(afegits)} / -{eliminats}")
