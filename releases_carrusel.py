import os, io, json, math, time
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ODOV Daily Hard Dance Releases - genera el carrusel de 2 imatges (1080x1920):
#   slide_01.png: gancho (portada desenfocada + "HARD DANCE RELEASE OF THE DAY")
#   slide_02.png: targeta estil reproductor amb portada, titol, artistes, etiqueta i "OUT TODAY"
# Entrada: variable d'entorn DATA (JSON) i, opcionalment, secrets de Spotify per completar dades i portada gran.

W, H = 1080, 1920
ACC = (0, 191, 255)
FONTS = os.path.expanduser(os.environ.get('FONTS_DIR', '~/fonts'))
BEBAS = os.path.join(FONTS, 'BebasNeue.ttf')
XB = os.path.join(FONTS, 'Montserrat-ExtraBold.ttf')
SB = os.path.join(FONTS, 'Montserrat-SemiBold.ttf')
MD = os.path.join(FONTS, 'Montserrat-Medium.ttf')
LOGO_PATH = 'logo.png'
LOGO_W, LOGO_Y, LOGO_OPACITY = 190, 140, 0.95
OUT_DIR = os.path.expanduser(os.environ.get('OUT_DIR', '~/output'))
NUMERO_PATH = 'releases_numero.json'

SP_ACCOUNTS = os.environ.get('SPOTIFY_ACCOUNTS', 'https://accounts.spotify.com').rstrip('/')
SP_API = os.environ.get('SPOTIFY_API', 'https://api.spotify.com/v1').rstrip('/')
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def font(p, s):
    return ImageFont.truetype(p, s)


# ---------------------------------------------------------------- dades
raw = os.environ.get('DATA', '').strip()
if not raw:
    raise SystemExit("Falta DATA")
D = json.loads(raw)
sid = (D.get('spotify_id') or '').strip()
titol = (D.get('titol') or '').strip()
artistes = D.get('artistes') or ''
if isinstance(artistes, list):
    artistes = ', '.join(artistes)
artistes = artistes.strip()
etiqueta = (D.get('etiqueta') if D.get('etiqueta') is not None else 'HARD DANCE').strip()
playlist_nom = (D.get('playlist_nom') or 'OneDayOneVibe | Daily Hard Dance Releases').strip()
try:
    numero = int(D.get('numero') or 0)
except Exception:
    numero = 0
portada_hdrr = (D.get('portada_hdrr') or '').strip()


def token_spotify():
    cid = os.environ.get('SPOTIFY_CLIENT_ID', '').strip()
    rt = os.environ.get('SPOTIFY_REFRESH_TOKEN', '').strip()
    if not (cid and rt):
        return ''
    try:
        r = requests.post(f"{SP_ACCOUNTS}/api/token", data={'grant_type': 'refresh_token', 'refresh_token': rt, 'client_id': cid}, timeout=25)
        if r.status_code == 200:
            return r.json().get('access_token', '')
        print(f"AVIS: token de Spotify {r.status_code}")
    except Exception as e:
        print(f"AVIS: token de Spotify: {e}")
    return ''


cover_url = ''
tk = token_spotify() if sid else ''
if tk:
    try:
        r = requests.get(f"{SP_API}/tracks/{sid}", headers={'Authorization': f'Bearer {tk}'}, timeout=25)
        if r.status_code == 200:
            j = r.json()
            if not titol:
                titol = j.get('name', '')
            if not artistes:
                artistes = ', '.join(a.get('name', '') for a in j.get('artists', []))
            imgs = sorted((j.get('album') or {}).get('images', []), key=lambda i: -(i.get('width') or 0))
            if imgs:
                cover_url = imgs[0]['url']
            print(f"Spotify: {titol} - {artistes}")
        else:
            print(f"AVIS: Spotify track {r.status_code} {r.text[:150]}")
    except Exception as e:
        print(f"AVIS: Spotify: {e}")

titol = titol or 'Title'
artistes = artistes or 'Artist'


def baixar(url):
    if not url:
        return None
    try:
        if os.path.exists(url):
            return Image.open(url).convert('RGB')
        r = requests.get(url if url.startswith('http') else 'https://www.hdrr.info' + url, headers=UA, timeout=30)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content)).convert('RGB')
        print(f"AVIS: portada {r.status_code} ({url[:80]})")
    except Exception as e:
        print(f"AVIS: portada: {e}")
    return None


cover = baixar(cover_url) or baixar(portada_hdrr)
if cover is None:
    print("AVIS: sense portada; faig servir un fons de substitucio")
    cover = Image.new('RGB', (640, 640), (20, 30, 60))
    d0 = ImageDraw.Draw(cover)
    for k in range(1, 7):
        d0.ellipse((320 - k * 45, 320 - k * 45, 320 + k * 45, 320 + k * 45), outline=(0, 140, 200), width=3)
cover = cover.resize((max(cover.width, 1), max(cover.height, 1)))
print(f"Portada {cover.width}x{cover.height}")


# ---------------------------------------------------------------- utilitats
def blur_bg(cv, bright):
    s = max(W / cv.width, H / cv.height)
    c = cv.resize((int(cv.width * s) + 1, int(cv.height * s) + 1), Image.LANCZOS)
    x = (c.width - W) // 2
    y = (c.height - H) // 2
    c = c.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(48))
    c = ImageEnhance.Color(c).enhance(1.15)
    return ImageEnhance.Brightness(c).enhance(bright)


def ctext(d, y, t, f, fill, stroke=0, sc=(0, 0, 0)):
    w = d.textlength(t, font=f)
    d.text(((W - w) / 2, y), t, font=f, fill=fill, stroke_width=stroke, stroke_fill=sc)


def fit(t, path, size, maxw):
    d = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    while size > 12 and d.textlength(t, font=font(path, size)) > maxw:
        size -= 2
    return font(path, size)


def ell(t, path, size, maxw):
    """Text amb punts suspensius si no hi cap."""
    f = font(path, size)
    d = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    if d.textlength(t, font=f) <= maxw:
        return t, f
    while t and d.textlength(t.rstrip() + '…', font=f) > maxw:
        t = t[:-1]
    return t.rstrip() + '…', f


def vignette(img):
    g = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(g)
    for i in range(0, 520):
        a = int(150 * (1 - i / 520) ** 2)
        d.rectangle((0, H - 1 - i, W, H - 1 - i), fill=a)
        d.rectangle((0, i, W, i), fill=int(a * 0.7))
    return Image.composite(Image.new('RGB', (W, H), (0, 0, 0)), img, g)


def pill(d, x, y, t, f, fg, bg, padx=26, h=58):
    w = d.textlength(t, font=f) + padx * 2
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=bg)
    d.text((x + padx, y + h / 2), t, font=f, fill=fg, anchor='lm')
    return w


def logo(img):
    if not os.path.exists(LOGO_PATH):
        return img
    try:
        lg = Image.open(LOGO_PATH).convert('RGBA')
        lg = lg.resize((LOGO_W, int(lg.height * LOGO_W / lg.width)), Image.LANCZOS)
        lg.putalpha(lg.split()[3].point(lambda p: int(p * LOGO_OPACITY)))
        im = img.convert('RGBA')
        im.alpha_composite(lg, ((W - LOGO_W) // 2, LOGO_Y))
        return im.convert('RGB')
    except Exception as e:
        print(f"AVIS: logo: {e}")
        return img


# ---------------------------------------------------------------- icones del reproductor
GREEN = (30, 215, 96)
SS = 2


def put(img, fn, cx, cy, size=100):
    L = Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0))
    fn(ImageDraw.Draw(L), size * SS / 2)
    ic = L.resize((size, size), Image.LANCZOS)
    img.paste(ic, (int(cx - size / 2), int(cy - size / 2)), ic)


def f_chev(d, c):
    s = SS
    d.line((c - 24 * s, c - 10 * s, c, c + 12 * s, c + 24 * s, c - 10 * s), fill=(255, 255, 255), width=7 * s, joint='curve')


def f_dots(d, c):
    s = SS
    for dx in (-24, 0, 24):
        d.ellipse((c + dx * s - 6 * s, c - 6 * s, c + dx * s + 6 * s, c + 6 * s), fill=(255, 255, 255))


def f_check(d, c):
    s = SS
    d.ellipse((c - 22 * s, c - 22 * s, c + 22 * s, c + 22 * s), fill=GREEN)
    d.line((c - 10 * s, c + 1 * s, c - 3 * s, c + 9 * s, c + 11 * s, c - 8 * s), fill=(0, 0, 0), width=5 * s, joint='curve')


def f_pause(d, c):
    s = SS
    d.ellipse((c - 62 * s, c - 62 * s, c + 62 * s, c + 62 * s), fill=(255, 255, 255))
    for dx in (-13, 13):
        d.rounded_rectangle((c + dx * s - 8 * s, c - 26 * s, c + dx * s + 8 * s, c + 26 * s), radius=3 * s, fill=(0, 0, 0))


def f_prev(d, c):
    s = SS
    d.polygon([(c - 2 * s, c), (c + 30 * s, c - 26 * s), (c + 30 * s, c + 26 * s)], fill=(255, 255, 255))
    d.rounded_rectangle((c - 34 * s, c - 26 * s, c - 26 * s, c + 26 * s), radius=2 * s, fill=(255, 255, 255))


def f_next(d, c):
    s = SS
    d.polygon([(c + 2 * s, c), (c - 30 * s, c - 26 * s), (c - 30 * s, c + 26 * s)], fill=(255, 255, 255))
    d.rounded_rectangle((c + 26 * s, c - 26 * s, c + 34 * s, c + 26 * s), radius=2 * s, fill=(255, 255, 255))


def f_shuffle(d, c):
    s = SS
    w = (255, 255, 255)
    lw = 5 * s
    d.line((c - 30 * s, c + 14 * s, c - 12 * s, c + 14 * s, c + 8 * s, c - 14 * s, c + 24 * s, c - 14 * s), fill=w, width=lw, joint='curve')
    d.line((c - 30 * s, c - 14 * s, c - 12 * s, c - 14 * s, c - 4 * s, c - 2 * s), fill=w, width=lw, joint='curve')
    d.line((c + 4 * s, c + 2 * s, c + 8 * s, c + 14 * s, c + 24 * s, c + 14 * s), fill=w, width=lw, joint='curve')
    d.polygon([(c + 22 * s, c - 26 * s), (c + 36 * s, c - 14 * s), (c + 22 * s, c - 2 * s)], fill=w)
    d.polygon([(c + 22 * s, c + 2 * s), (c + 36 * s, c + 14 * s), (c + 22 * s, c + 26 * s)], fill=w)


def f_repeat(d, c):
    s = SS
    w = (255, 255, 255)
    d.rounded_rectangle((c - 30 * s, c - 16 * s, c + 30 * s, c + 16 * s), radius=12 * s, outline=w, width=5 * s)
    d.rectangle((c + 8 * s, c - 22 * s, c + 40 * s, c - 8 * s), fill=(0, 0, 0, 0))
    d.polygon([(c + 14 * s, c - 30 * s), (c + 34 * s, c - 16 * s), (c + 14 * s, c - 2 * s)], fill=w)


# ---------------------------------------------------------------- imatge 1
def slide1():
    img = vignette(blur_bg(cover, 0.5))
    d = ImageDraw.Draw(img)
    f = font(XB, 34)
    w = d.textlength('NEW OUT TODAY', font=f) + 60
    d.rounded_rectangle(((W - w) / 2, 430, (W + w) / 2, 496), radius=33, fill=ACC)
    d.text((W / 2, 463), 'NEW OUT TODAY', font=f, fill=(0, 0, 0), anchor='mm')
    y = 560
    for t, col in (('HARD DANCE', (255, 255, 255)), ('RELEASE', (255, 255, 255)), ('OF THE DAY', ACC)):
        fo = fit(t, BEBAS, 330, 900)
        b = d.textbbox((0, 0), t, font=fo)
        ctext(d, y - b[1], t, fo, col, stroke=4)
        y += (b[3] - b[1]) + 34
    if numero > 0:
        ctext(d, 1270, f'#{numero:03d}', font(XB, 64), (255, 255, 255), stroke=2)
    d.text((W / 2 - 105, 1400), 'SWIPE', font=font(XB, 40), fill=(255, 255, 255), anchor='lm')
    ax = W / 2 + 60
    d.line((ax, 1400, ax + 70, 1400), fill=(255, 255, 255), width=7)
    d.polygon([(ax + 70, 1380), (ax + 104, 1400), (ax + 70, 1420)], fill=(255, 255, 255))
    return logo(img)


# ---------------------------------------------------------------- imatge 2
def dominant(cv):
    return cv.resize((1, 1), Image.BOX).getpixel((0, 0))


def grad_bg(col):
    r, g, b = col
    m = max(r, g, b, 1)
    k = 170 / m
    top = tuple(min(255, int(c * k * 0.85)) for c in (r, g, b))
    bot = (18, 18, 18)
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = min(1, max(0, (y - 120) / 1350)) ** 0.9
        d.line((0, y, W, y), fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    return img


def slide2():
    img = grad_bg(dominant(cover))
    put(img, f_chev, 110, 372, 80)
    put(img, f_dots, 970, 372, 100)
    d = ImageDraw.Draw(img, 'RGBA')
    ctext(d, 330, 'PLAYING FROM PLAYLIST', font(SB, 22), (220, 220, 220))
    nf = fit(playlist_nom, XB, 32, 730)
    ctext(d, 370, playlist_nom, nf, (255, 255, 255))
    X0, CW = 190, 700
    c = cover.resize((CW, CW), Image.LANCZOS)
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((X0, 450, X0 + CW, 450 + CW), radius=14, fill=(0, 0, 0, 150))
    sh = sh.filter(ImageFilter.GaussianBlur(30))
    img.paste(sh, (0, 24), sh)
    m = Image.new('L', (CW, CW), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, CW - 1, CW - 1), radius=14, fill=255)
    img.paste(c, (X0, 440), m)
    d = ImageDraw.Draw(img, 'RGBA')
    y = 440 + CW
    tt, tf = ell(titol, XB, 58, 620)
    d.text((X0, y + 85), tt, font=tf, fill=(255, 255, 255), anchor='ls')
    at, af = ell(artistes, SB, 38, CW)
    d.text((X0, y + 140), at, font=af, fill=(179, 179, 179), anchor='ls')
    put(img, f_check, X0 + CW - 22, y + 88, 70)
    d = ImageDraw.Draw(img, 'RGBA')
    fp = font(XB, 24)
    x = X0
    if etiqueta:
        et, _ = ell(etiqueta.upper(), XB, 24, 420)
        x += pill(d, x, y + 168, et, fp, (0, 0, 0), ACC, padx=22, h=50) + 12
    pill(d, x, y + 168, 'OUT TODAY', fp, (255, 255, 255), (255, 255, 255, 50), padx=22, h=50)
    py = y + 270
    d.rounded_rectangle((X0, py, X0 + CW, py + 7), radius=4, fill=(255, 255, 255, 80))
    px = X0 + int(CW * 0.38)
    d.rounded_rectangle((X0, py, px, py + 7), radius=4, fill=(255, 255, 255))
    d.ellipse((px - 10, py - 7, px + 10, py + 13), fill=(255, 255, 255))
    fs = font(MD, 24)
    d.text((X0, py + 40), '1:04', font=fs, fill=(167, 167, 167), anchor='lm')
    d.text((X0 + CW, py + 40), '-1:28', font=fs, fill=(167, 167, 167), anchor='rm')
    cy = py + 125
    put(img, f_shuffle, X0 + 10, cy, 90)
    put(img, f_prev, X0 + CW * 0.27, cy, 90)
    put(img, f_pause, W / 2, cy, 140)
    put(img, f_next, X0 + CW * 0.73, cy, 90)
    put(img, f_repeat, X0 + CW - 10, cy, 90)
    return logo(img)


os.makedirs(OUT_DIR, exist_ok=True)
for nom in ('slide_01.png', 'slide_02.png'):
    try:
        os.remove(os.path.join(OUT_DIR, nom))
    except OSError:
        pass
slide1().save(os.path.join(OUT_DIR, 'slide_01.png'))
slide2().save(os.path.join(OUT_DIR, 'slide_02.png'))
print(f"Imatges generades a {OUT_DIR}")

# recorda l'ultim numero d'edicio utilitzat (el web app el fa servir per proposar el seguent)
if numero > 0:
    try:
        with open(NUMERO_PATH, 'w', encoding='utf-8') as f:
            json.dump({'ultim': numero, 'spotify_id': sid, 'titol': titol, 'generat': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, f, ensure_ascii=False)
    except Exception as e:
        print(f"AVIS: no he pogut desar {NUMERO_PATH}: {e}")
