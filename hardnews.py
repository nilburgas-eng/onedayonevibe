import os, json, io, re
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Carrusel "Top Hard Dance News This Week": portada + una diapositiva per notícia + tancament (opcional).
# Entrada: DATA (JSON) amb:
#   week          text del rang de dates (ex: "OCT 26 - NOV 1")
#   cover_photo   ruta (al repo) de la foto de fons de la portada, o ""
#   outro         true/false: afegir diapositiva final "Follow"
#   stories       [{headline, summary, source, image_url, foto_path}]  (foto_path, si hi és, mana sobre image_url)

OUTPUT = os.path.expanduser("~/output")
FONTS  = os.path.expanduser("~/fonts")
os.makedirs(OUTPUT, exist_ok=True)

FONT_BEBAS     = f"{FONTS}/BebasNeue.ttf"
FONT_SEMIBOLD  = f"{FONTS}/Montserrat-SemiBold.ttf"
FONT_EXTRABOLD = f"{FONTS}/Montserrat-ExtraBold.ttf"
FONT_MEDIUM    = f"{FONTS}/Montserrat-Medium.ttf"
FONT_FALLBACK  = f"{FONTS}/Montserrat-Bold.ttf"

for _n in ("FONT_BEBAS", "FONT_SEMIBOLD", "FONT_EXTRABOLD", "FONT_MEDIUM"):
    _p = globals()[_n]
    if not os.path.exists(_p) or os.path.getsize(_p) < 1000:
        globals()[_n] = FONT_FALLBACK

W, H = 1080, 1920
COLOR_ACCENT = (0, 191, 255)
COLOR_WHITE  = (255, 255, 255)
COLOR_GREY   = (170, 170, 170)
BG_COLOR     = (13, 13, 13)

CONTENT_TOP    = 420    # TikTok tapa la part de dalt (cerca/hora) i el logo
CONTENT_BOTTOM = 1580   # i la de baix (compte, descripcio, punts del carrusel)
MARGE_X        = 90
TEXT_W         = W - 2 * MARGE_X

FOTO_Y = 330            # on comença la foto nítida a les diapositives de notícia
FOTO_H = 580
TEXT_Y0 = FOTO_Y + FOTO_H + 50

LOGO_PATH    = "logo.png"
LOGO_W       = 190
LOGO_OPACITY = 0.95
LOGO_Y       = 140
COMPTE       = "@onedayonevibe"

HEADERS_IMG = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


# ---------------------------------------------------------------- utilitats d'imatge
def cover_crop(img, tw, th):
    """Omple tw x th retallant pel centre (object-fit: cover)."""
    ratio, objectiu = img.width / img.height, tw / th
    if ratio > objectiu:
        nh, nw = th, int(th * ratio)
    else:
        nw, nh = tw, int(tw / ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    l, t = (nw - tw) // 2, (nh - th) // 2
    return img.crop((l, t, l + tw, t + th))


def fons_difuminat(foto, fosc=0.62):
    """Fons vertical 1080x1920 a partir de la foto, difuminat i enfosquit (la foto nítida va a sobre)."""
    g = cover_crop(foto.convert("RGB"), W, H)
    petit = g.resize((W // 6, H // 6), Image.LANCZOS).filter(ImageFilter.GaussianBlur(9))
    g = petit.resize((W, H), Image.BICUBIC)
    return Image.blend(g, Image.new("RGB", (W, H), (0, 0, 0)), fosc)


def fons_buit():
    """Fons de reserva quan no hi ha cap foto: negre amb un degradat suau cian a dalt."""
    img = Image.new("RGB", (W, H), BG_COLOR)
    mascara = Image.linear_gradient("L").transpose(Image.FLIP_TOP_BOTTOM).resize((W, 900)).point(lambda v: int(v * 0.22))
    img.paste(Image.new("RGB", (W, 900), COLOR_ACCENT), (0, 0), mascara)
    return img


def degradat_vertical(img, y0, y1, alfa0, alfa1):
    """Franja negra amb opacitat que va de alfa0 (a y0) a alfa1 (a y1)."""
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    px = capa.load()
    for y in range(max(0, y0), min(img.height, y1)):
        t = (y - y0) / max(1, (y1 - y0))
        a = int(255 * (alfa0 + (alfa1 - alfa0) * t))
        for x in range(img.width):
            px[x, y] = (0, 0, 0, a)
    return Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB")


def afegir_logo(img, w=LOGO_W, y=LOGO_Y):
    if not os.path.exists(LOGO_PATH):
        return img
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((w, int(logo.height * w / logo.width)), Image.LANCZOS)
        alfa = logo.split()[3].point(lambda p: int(p * LOGO_OPACITY))
        logo.putalpha(alfa)
        img = img.convert("RGBA")
        img.alpha_composite(logo, ((W - w) // 2, y))
        return img.convert("RGB")
    except Exception as e:
        print(f"   AVIS: no s'ha pogut afegir el logo: {e}")
        return img


# ---------------------------------------------------------------- utilitats de text
def font(path, mida):
    try:
        return ImageFont.truetype(path, mida)
    except Exception:
        return ImageFont.load_default()


def amplada(draw, text, f):
    b = draw.textbbox((0, 0), text, font=f)
    return b[2] - b[0]


def embolicar(draw, text, f, max_w):
    linies, actual = [], ""
    for p in text.split():
        prova = (actual + " " + p).strip()
        if amplada(draw, prova, f) <= max_w:
            actual = prova
        else:
            if actual:
                linies.append(actual)
            actual = p
    if actual:
        linies.append(actual)
    return linies


def ajustar(draw, text, path, mides, max_w, max_h, interlineat=1.2, max_linies=None):
    """Primera mida (de gran a petita) amb la qual el text cap dins max_w x max_h."""
    for mida in mides:
        f = font(path, mida)
        linies = embolicar(draw, text, f, max_w)
        if max_linies and len(linies) > max_linies:
            continue
        if len(linies) * mida * interlineat <= max_h:
            return f, linies, mida * interlineat
    mida = mides[-1]
    f = font(path, mida)
    return f, embolicar(draw, text, f, max_w), mida * interlineat


def text_esq(draw, linies, f, x, y, alcada, color):
    for l in linies:
        draw.text((x, y), l, font=f, fill=color)
        y += alcada
    return y


def font_ajustada(draw, text, path, mida_max, max_w, mida_min=30):
    """Mida de font mes gran (<= mida_max) amb la qual el text cap en una sola linia de max_w."""
    m = mida_max
    while m > mida_min and amplada(draw, text, font(path, m)) > max_w:
        m -= 4
    return font(path, m)


def text_centre(draw, text, f, y, color, ombra=True):
    x = (W - amplada(draw, text, f)) / 2
    if ombra:
        draw.text((x + 3, y + 4), text, font=f, fill=(0, 0, 0))
    draw.text((x, y), text, font=f, fill=color)


# ---------------------------------------------------------------- carrega de fotos
def carregar_foto(origen, referer=''):
    """Obre una foto des d'una ruta del repo o d'una URL. Torna None si no es pot."""
    if not origen:
        return None
    try:
        if origen.startswith('http'):
            h = dict(HEADERS_IMG)
            if referer:
                h["Referer"] = referer
            r = requests.get(origen, headers=h, timeout=30)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
        elif os.path.exists(origen) and os.path.getsize(origen) > 500:
            img = Image.open(origen)
        else:
            print(f"   AVIS: no trobo la foto {origen}")
            return None
        img = img.convert("RGB")
        if img.width < 200 or img.height < 200:
            print(f"   AVIS: la foto es massa petita ({img.width}x{img.height})")
            return None
        return img
    except Exception as e:
        print(f"   AVIS: no s'ha pogut carregar la foto ({type(e).__name__}: {e})")
        return None


# ---------------------------------------------------------------- diapositives
def diapositiva_portada(week, n, foto):
    if foto is not None:
        img = cover_crop(foto, W, H)
        img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.50)
    else:
        img = fons_buit()
    img = degradat_vertical(img, CONTENT_TOP - 80, CONTENT_BOTTOM + 60, 0.15, 0.55)
    d = ImageDraw.Draw(img)

    linies = [("TOP HARD DANCE", 150, COLOR_WHITE), ("NEWS", 330, COLOR_ACCENT), ("THIS WEEK", 150, COLOR_WHITE)]
    fonts = []
    for text, mida_max, color in linies:
        m = mida_max
        while m > 40 and amplada(d, text, font(FONT_BEBAS, m)) > TEXT_W + 20:
            m -= 4
        fonts.append((text, font(FONT_BEBAS, m), m, color))
    alcada_total = sum(m * 0.98 for _, _, m, _ in fonts)
    y = CONTENT_TOP + 70 + ((CONTENT_BOTTOM - CONTENT_TOP - 70 - 230) - alcada_total) / 2
    for text, f, m, color in fonts:
        text_centre(d, text, f, y, color)
        y += m * 0.98

    # filet + dates
    y += 28
    d.rectangle([(W // 2 - 90, y), (W // 2 + 90, y + 8)], fill=COLOR_ACCENT)
    y += 40
    if week:
        text_centre(d, week.upper(), font(FONT_EXTRABOLD, 46), y, COLOR_WHITE)
        y += 74
    text_centre(d, f"{n} STORIES", font(FONT_SEMIBOLD, 34), y, COLOR_ACCENT)

    # "SWIPE" + fletxa dibuixada (no depen de cap glif de la font)
    ys = CONTENT_BOTTOM - 70
    fs = font(FONT_SEMIBOLD, 34)
    ws = amplada(d, "SWIPE", fs)
    x0 = (W - (ws + 70)) / 2
    d.text((x0, ys), "SWIPE", font=fs, fill=COLOR_WHITE)
    xa, ya = x0 + ws + 20, ys + 26
    d.line([(xa, ya), (xa + 44, ya)], fill=COLOR_WHITE, width=5)
    d.line([(xa + 44, ya), (xa + 30, ya - 14)], fill=COLOR_WHITE, width=5)
    d.line([(xa + 44, ya), (xa + 30, ya + 14)], fill=COLOR_WHITE, width=5)
    return afegir_logo(img)


def diapositiva_noticia(idx, total, story, foto):
    if foto is not None:
        img = fons_difuminat(foto)
        card = cover_crop(foto, W, FOTO_H)
        img.paste(card, (0, FOTO_Y))
    else:
        img = fons_buit()
    img = degradat_vertical(img, FOTO_Y + FOTO_H, H, 0.30, 0.65)
    d = ImageDraw.Draw(img)
    if foto is not None:
        d.rectangle([(0, FOTO_Y + FOTO_H), (W, FOTO_Y + FOTO_H + 7)], fill=COLOR_ACCENT)
    # etiqueta "NEWS 1/5"
    y = TEXT_Y0
    d.text((MARGE_X, y), f"NEWS {idx}/{total}", font=font(FONT_EXTRABOLD, 30), fill=COLOR_ACCENT)
    y += 56

    espai_font = 56
    fons_h = CONTENT_BOTTOM - y - espai_font
    headline = story.get('headline', '').upper()
    summary = story.get('summary', '')

    fh, lh, ah = ajustar(d, headline, FONT_BEBAS, [104, 96, 88, 80, 72, 64, 58, 52],
                         TEXT_W, 330, interlineat=1.0, max_linies=3)
    y = text_esq(d, lh, fh, MARGE_X, y, ah, COLOR_WHITE)
    y += 14
    d.rectangle([(MARGE_X, y), (MARGE_X + 120, y + 7)], fill=COLOR_ACCENT)
    y += 30

    resta = (CONTENT_BOTTOM - espai_font) - y
    fs, ls, a_s = ajustar(d, summary, FONT_SEMIBOLD, [44, 42, 40, 38, 36, 34, 32, 30, 28, 26],
                          TEXT_W, resta, interlineat=1.32)
    text_esq(d, ls, fs, MARGE_X, y, a_s, (235, 235, 235))

    font_src = story.get('source', '').strip()
    if font_src:
        d.text((MARGE_X, CONTENT_BOTTOM - 40), f"Source: {font_src}", font=font(FONT_MEDIUM, 27), fill=COLOR_GREY)
    return afegir_logo(img)


def diapositiva_final(foto):
    if foto is not None:
        img = fons_difuminat(foto, fosc=0.70)
    else:
        img = fons_buit()
    d = ImageDraw.Draw(img)
    mid = (CONTENT_TOP + CONTENT_BOTTOM) / 2
    f1 = font_ajustada(d, "NEVER MISS A WEEK", FONT_BEBAS, 120, TEXT_W)
    f2 = font_ajustada(d, "FOLLOW", FONT_BEBAS, 300, TEXT_W)
    f3 = font_ajustada(d, COMPTE, FONT_EXTRABOLD, 60, TEXT_W)
    f4 = font_ajustada(d, "for weekly hard dance news", FONT_SEMIBOLD, 38, TEXT_W)
    text_centre(d, "NEVER MISS A WEEK", f1, mid - 270, COLOR_WHITE)
    text_centre(d, "FOLLOW", f2, mid - 150, COLOR_ACCENT)
    text_centre(d, COMPTE, f3, mid + 150, COLOR_WHITE)
    text_centre(d, "for weekly hard dance news", f4, mid + 235, (210, 210, 210))
    return afegir_logo(img)


# ---------------------------------------------------------------- principal
RAW = os.environ.get('DATA', '').strip()
if not RAW:
    print("ERROR: falta DATA")
    exit(1)
dades = json.loads(RAW)

week = dades.get('week', '').strip()
stories = [s for s in dades.get('stories', []) if s.get('headline') and s.get('summary')]
if not stories:
    print("ERROR: no hi ha cap notícia amb titular i resum")
    exit(1)
total = len(stories)
print(f"Notícies: {total} | setmana: {week or '(sense)'}")

# fotos de cada notícia
fotos = []
for i, s in enumerate(stories, 1):
    print(f"\nNotícia {i}: {s['headline']}")
    f = carregar_foto(s.get('foto_path'))
    origen = 'manual' if f is not None else ''
    if f is None:
        f = carregar_foto(s.get('image_url'), referer=s.get('url', ''))
        origen = 'article' if f is not None else ''
    if f is None:
        print("   AVIS: sense foto, es fa servir el fons per defecte (puja'n una a la web app)")
    else:
        print(f"   Foto {origen}: {f.width}x{f.height}")
    fotos.append(f)

foto_portada = carregar_foto(dades.get('cover_photo'))
if foto_portada is not None:
    print(f"\nFoto de portada manual: {foto_portada.width}x{foto_portada.height}")
else:
    foto_portada = next((f for f in fotos if f is not None), None)
    print("\nPortada: sense foto manual" + (" (faig servir la de la primera notícia)" if foto_portada is not None else " (fons per defecte)"))

for fitxer in os.listdir(OUTPUT):
    if fitxer.startswith("slide_") and fitxer.endswith(".png"):
        os.remove(os.path.join(OUTPUT, fitxer))

diapositiva_portada(week, total, foto_portada).save(f"{OUTPUT}/slide_00_cover.png", "PNG")
print("\nPortada generada")
for i, (s, f) in enumerate(zip(stories, fotos), 1):
    diapositiva_noticia(i, total, s, f).save(f"{OUTPUT}/slide_{i:02d}.png", "PNG")
    print(f"Diapositiva {i}/{total} generada")
if dades.get('outro', True):
    diapositiva_final(foto_portada).save(f"{OUTPUT}/slide_90_outro.png", "PNG")
    print("Diapositiva final generada")

print("\nTot generat correctament!")
