# odov_comu.py - funcions compartides pels formats de video d'ODOV
#  1) PORTADES: Spotify -> Deezer -> iTunes (mai posa la portada d'un altre tema; prova tambe nom/artista girats)
#  2) TEXT: ajust al pixel amb punts suspensius, capcalera centrada, degradats suaus, fitxa del tema
# Va a l'arrel del repo, al costat dels altres .py.
import os, re, time, base64, unicodedata
import requests
from PIL import ImageFont

# ======================================================================================
#  ZONA SEGURA (mides del video 1080x1920, comprovades amb captures de TikTok)
#   - a dalt, la barra de cerca de TikTok ocupa fins a y ~ 235
#   - als costats, TikTok retalla uns 55 px
#   - a baix, la descripcio comenca cap a y ~ 1560, i les icones de la dreta (x > 905) entre y ~ 940 i 1640
# ======================================================================================
Y_SEGUR_DALT = 240
X_SEGUR_DRETA = 1000


# ======================================================================================
#  PORTADES
# ======================================================================================
def _sense_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s or '')) if unicodedata.category(c) != 'Mn')


def _titol_base(s):
    s = _sense_accents(s).lower()
    s = re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', s)
    s = re.sub(r'\s[-–—]\s.*$', ' ', s)
    s = re.sub(r'\b(feat|ft|featuring)\b.*$', ' ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def _artistes_llista(s):
    s = _sense_accents(s).lower()
    parts = re.split(r',|&|\+|/|\bfeat\.?(?=\s|$)|\bft\.?(?=\s|$)|\bfeaturing\b|\bvs\.?(?=\s|$)|\bwith\b|\bx\b', s)
    out = []
    for p in parts:
        p = re.sub(r'[^a-z0-9]+', ' ', p).strip()
        if p:
            out.append(p)
    return out


def _coincideix(nom, artista, nom_trobat, artistes_trobats):
    """Titol igual (sense versions) i almenys un artista en comu."""
    if not _titol_base(nom) or _titol_base(nom) != _titol_base(nom_trobat):
        return False
    meus = _artistes_llista(artista)
    seus = []
    for a in artistes_trobats:
        seus.extend(_artistes_llista(a))
    if not meus or not seus:
        return True
    for a in meus:
        for b in seus:
            if a == b or (len(a) > 3 and len(b) > 3 and (a in b or b in a)):
                return True
    return False


def _get(url, headers=None, params=None, intents=3):
    for _ in range(intents):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code == 429:
                espera = min(int(r.headers.get('Retry-After', '2') or 2), 10)
                print(f"   (429, espero {espera}s)")
                time.sleep(espera + 0.5)
                continue
            return r
        except Exception as e:
            print(f"   (error de xarxa: {e})")
            time.sleep(1.5)
    return None


def _baixar(url):
    r = _get(url)
    if r is not None and r.status_code == 200 and len(r.content) > 2000:
        return r.content
    return None


def _cerques(nom, artista):
    titol = re.sub(r'\s+', ' ', re.sub(r'\([^)]*\)|\[[^\]]*\]|\s[-–—]\s.*$', ' ', nom or '')).strip() or (nom or '')
    arts = [a.strip() for a in re.split(r',|&|\bfeat\.?(?=\s|$)|\bft\.?(?=\s|$)|\bx\b', artista or '') if a.strip()]
    return titol, (arts[0] if arts else '')


def spotify_token(client_id, secret):
    try:
        creds = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        r = requests.post("https://accounts.spotify.com/api/token", headers={"Authorization": f"Basic {creds}"},
                          data={"grant_type": "client_credentials"}, timeout=20)
        if r.status_code != 200:
            print(f"   AVIS: token de Spotify {r.status_code} {r.text[:150]}")
            return None
        return r.json().get('access_token')
    except Exception as e:
        print(f"   AVIS: token de Spotify: {e}")
        return None


def _cover_spotify(nom, artista, token):
    if not token:
        return None
    titol, primer = _cerques(nom, artista)
    headers = {"Authorization": f"Bearer {token}"}
    consultes = [f"track:{titol} artist:{primer}" if primer else f"track:{titol}",
                 f"{titol} {primer}".strip(), f"{titol} {artista}".strip()]
    vistes = set()
    for q in consultes:
        if q in vistes:
            continue
        vistes.add(q)
        r = _get("https://api.spotify.com/v1/search", headers=headers, params={"q": q, "type": "track", "limit": 10})
        if r is None or r.status_code != 200:
            print(f"   Spotify cerca '{q[:50]}': {'sense resposta' if r is None else str(r.status_code) + ' ' + r.text[:120]}")
            continue
        try:
            items = r.json().get('tracks', {}).get('items', [])
        except Exception:
            items = []
        for it in items:
            if _coincideix(nom, artista, it.get('name', ''), [a.get('name', '') for a in it.get('artists', [])]):
                imgs = it.get('album', {}).get('images', [])
                if imgs:
                    d = _baixar(imgs[0]['url'])
                    if d:
                        return d
    return None


def _cover_deezer(nom, artista):
    titol, primer = _cerques(nom, artista)
    for q in ([f'track:"{titol}" artist:"{primer}"'] if primer else []) + [f"{titol} {primer}".strip()]:
        r = _get("https://api.deezer.com/search", params={"q": q, "limit": 10})
        if r is None or r.status_code != 200:
            continue
        try:
            items = r.json().get('data', [])
        except Exception:
            items = []
        for it in items:
            if _coincideix(nom, artista, it.get('title', ''), [it.get('artist', {}).get('name', '')]):
                alb = it.get('album', {})
                for k in ('cover_xl', 'cover_big', 'cover_medium'):
                    if alb.get(k):
                        d = _baixar(alb[k])
                        if d:
                            return d
    return None


def _cover_itunes(nom, artista):
    titol, primer = _cerques(nom, artista)
    r = _get("https://itunes.apple.com/search", params={"term": f"{titol} {primer}".strip(), "entity": "song", "limit": 10})
    if r is None or r.status_code != 200:
        return None
    try:
        items = r.json().get('results', [])
    except Exception:
        items = []
    for it in items:
        if _coincideix(nom, artista, it.get('trackName', ''), [it.get('artistName', '')]):
            url = it.get('artworkUrl100', '')
            if url:
                d = _baixar(url.replace('100x100bb', '1000x1000bb')) or _baixar(url)
                if d:
                    return d
    return None


def obtenir_portada(nom, artista, token=None):
    """Torna (bytes, font) o (None, None). Prova Spotify, Deezer i iTunes; si no troba res, tambe amb nom i artista girats
    (per si a la web s'han escrit al reves). Mai posa la portada d'un altre tema."""
    for a, b, girat in ((nom, artista, False), (artista, nom, True)):
        if not a or not b:
            continue
        for f, nomf in ((lambda: _cover_spotify(a, b, token), 'Spotify'), (lambda: _cover_deezer(a, b), 'Deezer'),
                        (lambda: _cover_itunes(a, b), 'iTunes')):
            d = f()
            if d:
                return d, nomf + (' (nom i artista girats)' if girat else '')
    return None, None


def foto_artista_spotify(artista, token):
    if not artista or not token:
        return None
    _, primer = _cerques('x', artista)
    r = _get("https://api.spotify.com/v1/search", headers={"Authorization": f"Bearer {token}"},
             params={"q": primer or artista, "type": "artist", "limit": 5})
    if r is None or r.status_code != 200:
        return None
    try:
        items = r.json().get('artists', {}).get('items', [])
    except Exception:
        return None
    ref = (_artistes_llista(primer or artista) or [''])[0]
    for it in items:
        n = _artistes_llista(it.get('name', ''))
        if it.get('images') and n and n[0] == ref:
            return _baixar(it['images'][0]['url'])
    return None


# ======================================================================================
#  TEXT: mesures, punts suspensius, capcalera, fitxa del tema, degradats
# ======================================================================================
_fonts = {}


def _font(path, mida):
    k = (path, int(mida))
    if k not in _fonts:
        try:
            _fonts[k] = ImageFont.truetype(path, int(mida))
        except Exception:
            _fonts[k] = None
    return _fonts[k]


def mesura(text, font_path, mida):
    f = _font(font_path, mida)
    if f is None:
        return len(text) * mida * 0.55
    return f.getlength(text)


def neteja(t):
    """Mateixa neteja que feien els scripts abans (cometes i dos punts), sense tocar res mes."""
    return str(t or '').replace("'", "").replace('"', '').replace(':', '-')


def retalla(text, font_path, mida, ample):
    """Retalla amb '...' si no hi cap."""
    text = text.strip()
    if mesura(text, font_path, mida) <= ample:
        return text
    while len(text) > 1 and mesura(text + '...', font_path, mida) > ample:
        text = text[:-1].rstrip()
    return text + '...'


def parteix_linies(text, font_path, mida, ample, max_linies=2):
    """Parteix per paraules segons l'amplada real; si encara no hi cap, l'ultima linia acaba en '...'."""
    paraules = text.split()
    linies, cur = [], ''
    i = 0
    while i < len(paraules):
        prova = (cur + ' ' + paraules[i]).strip()
        if mesura(prova, font_path, mida) <= ample or not cur:
            cur = prova
            i += 1
        else:
            linies.append(cur)
            cur = ''
            if len(linies) == max_linies - 1:
                break
    resta = ' '.join(([cur] if cur else []) + paraules[i:]) if len(linies) == max_linies - 1 else cur
    if resta:
        linies.append(retalla(resta, font_path, mida, ample))
    return [l for l in linies if l] or ['']


def _alcada_visible(font_path, mida):
    """(dalt_visible, baix_visible) de les majuscules respecte el punt y de drawtext."""
    f = _font(font_path, mida)
    if f is None:
        return mida * 0.2, mida * 0.9
    b = f.getbbox('H', anchor='la')
    return b[1], b[3]


def dt(text, font, mida, color, x, y, vora=3, ombra=2, vora_color='black@0.9', extra=''):
    return (f"drawtext=fontfile='{font}':text='{text}':fontsize={int(mida)}:fontcolor={color}:borderw={vora}:"
            f"bordercolor={vora_color}:shadowcolor=black@0.5:shadowx=0:shadowy={ombra}:x={x}:y={int(y)}{extra}")


def degradat_dalt(alt, alfa_max, passos=30):
    """Fosc a dalt que s'esvaeix cap avall (en lloc d'una franja amb vora dura)."""
    out = []
    for i in range(passos):
        y0 = int(alt * i / passos)
        h = int(alt * (i + 1) / passos) - y0
        a = alfa_max * (1 - (i + 0.5) / passos) ** 1.5
        out.append(f"drawbox=x=0:y={y0}:w=1080:h={max(h, 1)}:color=black@{a:.3f}:t=fill")
    return out


def degradat_baix(y_ini, alfa_max, passos=30, y_fi=1920):
    out = []
    alt = y_fi - y_ini
    for i in range(passos):
        y0 = int(y_ini + alt * i / passos)
        h = int(y_ini + alt * (i + 1) / passos) - y0
        a = alfa_max * ((i + 0.5) / passos) ** 1.5
        out.append(f"drawbox=x=0:y={y0}:w=1080:h={max(h, 1)}:color=black@{a:.3f}:t=fill")
    return out


def capcalera(items, zona=(Y_SEGUR_DALT, 478), ample_max=920, centre_x=540):
    """Apila els textos del titol i els centra VERTICALMENT dins la zona (tambe quan no hi ha subtitol).
    items: llista de dicts amb: text, font, mida, color, [gap] (px abans de la linia), [filets] (True = linies als costats)
    Si una linia no hi cap en amplada, redueix la mida (nomes d'aquella linia, fins al 60%).
    Torna (filtres, y_baix)."""
    items = [dict(i) for i in items if i.get('text')]
    if not items:
        return [], zona[0]
    for it in items:
        m = it['mida']
        while m > it['mida'] * 0.6 and mesura(it['text'], it['font'], m) > ample_max:
            m -= 2
        it['mida_f'] = m
        it['dalt'], it['baix'] = _alcada_visible(it['font'], m)
    # alcada visible de cada linia i espais
    total = 0
    for k, it in enumerate(items):
        it['alt'] = it['baix'] - it['dalt']
        total += it['alt'] + (it.get('gap', 14) if k else 0)
    y = zona[0] + max(0, ((zona[1] - zona[0]) - total) / 2)
    filtres, y_vis = [], y
    for k, it in enumerate(items):
        if k:
            y_vis += it.get('gap', 14)
        y_text = y_vis - it['dalt']
        filtres.append(dt(it['text'], it['font'], it['mida_f'], it['color'], '(w-text_w)/2', y_text,
                          vora=it.get('vora', 3), ombra=it.get('ombra', 4), vora_color='black@0.85'))
        if it.get('filets'):
            w = mesura(it['text'], it['font'], it['mida_f'])
            cy = int(y_vis + it['alt'] / 2)
            llarg = int(min(110, max(0, (ample_max - w) / 2 - 30)))
            if llarg >= 40:
                col = it.get('filet_color', it['color'])
                filtres.append(f"drawbox=x={int(centre_x - w / 2 - 30 - llarg)}:y={cy}:w={llarg}:h=4:color={col}@0.85:t=fill")
                filtres.append(f"drawbox=x={int(centre_x + w / 2 + 30)}:y={cy}:w={llarg}:h=4:color={col}@0.85:t=fill")
        y_vis += it['alt']
    return filtres, y_vis


def titol_en_linies(text, font_path, mida_max=84, mida_min=56, ample=920):
    """Escull la lletra mes gran possible: una linia si hi cap; si no, 2 linies equilibrades. Torna (linies, mida)."""
    text = neteja(text).strip()
    if not text:
        return [], mida_max
    for m in range(mida_max, mida_min - 1, -4):
        if mesura(text, font_path, m) <= ample:
            return [text], m
    paraules = text.split()
    if len(paraules) >= 2:
        millor = None
        for i in range(1, len(paraules)):
            l1, l2 = ' '.join(paraules[:i]), ' '.join(paraules[i:])
            pitjor = max(mesura(l1, font_path, mida_max), mesura(l2, font_path, mida_max))
            if millor is None or pitjor < millor[0]:
                millor = (pitjor, l1, l2)
        _, l1, l2 = millor
        for m in range(min(mida_max, 80), mida_min - 1, -4):
            if max(mesura(l1, font_path, m), mesura(l2, font_path, m)) <= ample:
                return [l1, l2], m
        return [l1, l2], mida_min
    return [text], mida_min


def fitxa(pos, nom, artista, x_info, y_num, fonts, ample_max=None, color_num='white', mida_num=130,
          mida_nom=50, mida_art=38, color_art='white@0.9'):
    """Numero, nom del tema (fins a 2 linies, amb '...') i artista (amb '...') al costat de la portada.
    fonts = dict(extrabold=, semibold=, medium=). Torna (filtres, y_final_text, ample_disponible)."""
    ample = ample_max if ample_max else (X_SEGUR_DRETA - x_info)
    f = []
    f.append(dt(f"#{pos}", fonts['extrabold'], mida_num, color_num, x_info, y_num, vora=3, ombra=3))
    nom_net = neteja(nom)
    # primer es prova d'escriure'l en una sola linia, reduint una mica la lletra; si no hi cap, 2 linies
    linies = None
    for m in (mida_nom, mida_nom - 3, mida_nom - 6):
        if mesura(nom_net, fonts['semibold'], m) <= ample:
            linies, mida_nom = [nom_net], m
            break
    if linies is None:
        mida_nom = mida_nom - 4
        linies = parteix_linies(nom_net, fonts['semibold'], mida_nom, ample, 2)
    pas = int(mida_nom * 1.16)
    y = y_num + 140
    for l in linies:
        f.append(dt(l, fonts['semibold'], mida_nom, 'white', x_info, y, vora=3, ombra=2))
        y += pas
    y_art = y + 6
    art = retalla(neteja(artista), fonts['medium'], mida_art, ample) if artista else ''
    if art:
        f.append(dt(art, fonts['medium'], mida_art, color_art, x_info, y_art, vora=2, ombra=2, vora_color='black@0.8'))
    return f, (y_art + mida_art if art else y), ample
