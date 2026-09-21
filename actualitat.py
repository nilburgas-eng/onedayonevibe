import os, json, re, base64, textwrap
import requests
from PIL import Image, ImageDraw, ImageFont
from readability import Document
import anthropic

OUTPUT = os.path.expanduser("~/output")
FONTS  = os.path.expanduser("~/fonts")
os.makedirs(OUTPUT, exist_ok=True)

FONT_BEBAS     = f"{FONTS}/BebasNeue.ttf"
FONT_SEMIBOLD  = f"{FONTS}/Montserrat-SemiBold.ttf"
FONT_EXTRABOLD = f"{FONTS}/Montserrat-ExtraBold.ttf"
FONT_MEDIUM    = f"{FONTS}/Montserrat-Medium.ttf"
FONT_FALLBACK  = f"{FONTS}/Montserrat-Bold.ttf"

for font_path in [FONT_BEBAS, FONT_SEMIBOLD, FONT_EXTRABOLD, FONT_MEDIUM]:
    if not os.path.exists(font_path) or os.path.getsize(font_path) < 1000:
        if font_path == FONT_BEBAS: FONT_BEBAS = FONT_FALLBACK
        elif font_path == FONT_SEMIBOLD: FONT_SEMIBOLD = FONT_FALLBACK
        elif font_path == FONT_EXTRABOLD: FONT_EXTRABOLD = FONT_FALLBACK
        elif font_path == FONT_MEDIUM: FONT_MEDIUM = FONT_FALLBACK

URL_NOTICIA   = os.environ.get('URL_NOTICIA', '').strip()
TEXT_MANUAL   = os.environ.get('TEXT_MANUAL', '').strip()
FOTO1_URL     = os.environ.get('FOTO1_URL', '').strip()
FOTO2_URL     = os.environ.get('FOTO2_URL', '').strip()
INSTRUCCIONS_EXTRA = os.environ.get('INSTRUCCIONS_EXTRA', '').strip()
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')

W, H = 1080, 1920
BG_COLOR     = (13, 13, 13)
COLOR_ACCENT = (0, 191, 255)
COLOR_WHITE  = (255, 255, 255)

Y_KICKER   = 260
Y_TITOL    = 330
BOX_TOP_H  = 440
BOX_BOT_Y  = 1580
BOX_BOT_H  = 340
Y_RESUM    = 1660

LOGO_PATH    = "logo.png"
LOGO_W       = 90
LOGO_OPACITY = 0.85
LOGO_MARGIN  = 30
LOGO_ACTIU   = os.path.exists(LOGO_PATH)


def cover_crop(img, target_w, target_h):
    """Escala i retalla la imatge perque ompli exactament target_w x target_h, com un 'object-fit: cover'."""
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * img_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / img_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def preparar_fons(foto_local_path, darken=0.45):
    """Baixa/obre la foto, la retalla per omplir 1080x1920 i l'enfosqueix perque el text es llegeixi be."""
    img = Image.open(foto_local_path).convert("RGB")
    img = cover_crop(img, W, H)
    negre = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(img, negre, darken)
    return img


def caixa_semitransparent(img, box, opacitat=0.35):
    """Dibuixa un rectangle negre semitransparent sobre la imatge, per reforçar contrast del text."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    alpha = int(255 * opacitat)
    draw.rectangle(box, fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def get_text_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def amplada_text(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def embolicar_text(draw, text, font, max_width):
    """Parteix el text en linies que caben dins max_width."""
    paraules = text.split()
    linies = []
    linia_actual = ""
    for paraula in paraules:
        prova = (linia_actual + " " + paraula).strip()
        if amplada_text(draw, prova, font) <= max_width:
            linia_actual = prova
        else:
            if linia_actual:
                linies.append(linia_actual)
            linia_actual = paraula
    if linia_actual:
        linies.append(linia_actual)
    return linies


def ajustar_bloc_text(draw, text, font_path, mides, max_width, max_height, interlineat=1.25):
    """Prova mides de font decreixents fins que el text (embolicat) cap dins max_height."""
    for mida in mides:
        font = get_text_font(font_path, mida)
        linies = embolicar_text(draw, text, font, max_width)
        alcada_linia = mida * interlineat
        alcada_total = alcada_linia * len(linies)
        if alcada_total <= max_height:
            return font, linies, alcada_linia
    # si no hi cap res, es fa servir la mida minima igualment
    mida = mides[-1]
    font = get_text_font(font_path, mida)
    linies = embolicar_text(draw, text, font, max_width)
    return font, linies, mida * interlineat


def dibuixar_bloc_centrat(draw, linies, font, y_inici, alcada_linia, color, w_canvas=W):
    y = y_inici
    for linia in linies:
        amplada = amplada_text(draw, linia, font)
        x = (w_canvas - amplada) / 2
        draw.text((x, y), linia, font=font, fill=color)
        y += alcada_linia
    return y


def afegir_logo(img):
    if not LOGO_ACTIU:
        return img
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        ratio = LOGO_W / logo.width
        logo = logo.resize((LOGO_W, int(logo.height * ratio)))
        if LOGO_OPACITY < 1.0:
            alpha = logo.split()[3].point(lambda p: int(p * LOGO_OPACITY))
            logo.putalpha(alpha)
        x = W - LOGO_W - LOGO_MARGIN
        y = LOGO_MARGIN
        img.paste(logo, (x, y), logo)
    except Exception as e:
        print(f"AVIS: no s'ha pogut afegir el logo: {e}")
    return img


def extreure_article(url):
    """Baixa la pagina i n'extreu el titol i el text principal, ignorant menus/anuncis."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; onedayonevibe-bot/1.0)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    doc = Document(r.text)
    titol = doc.title()
    html_net = doc.summary()
    text_net = re.sub(r'<[^>]+>', ' ', html_net)
    text_net = re.sub(r'\s+', ' ', text_net).strip()
    return titol, text_net


def generar_contingut_ia(titol_font, text_font, url, client, instruccions_extra=''):
    instruccions_bloc = ""
    if instruccions_extra:
        instruccions_bloc = (
            "\nIMPORTANT extra instructions from the editor (follow these carefully, "
            f"they override the general rules if they conflict):\n{instruccions_extra}\n"
        )
    prompt = (
        "You are the social media editor for @onedayonevibe, an EDM/Hardstyle TikTok account. "
        "Based on the article below, create content for a 2-slide news carousel.\n\n"
        "Rules:\n"
        "- Write in your OWN words. Never copy sentences verbatim from the source.\n"
        "- HEADLINE: punchy, max 60 characters, in English, no quotation marks.\n"
        "- SUMMARY: 2-3 short sentences, max 280 characters total, in English, factual and neutral tone.\n"
        "- CAPTION: one short extra sentence for the TikTok description (max 150 characters), in English.\n"
        "- HASHTAGS: exactly 4 relevant lowercase hashtags (no spaces), based on the specific content "
        "(festival name, artist, genre, event) - not generic filler.\n"
        f"{instruccions_bloc}\n"
        "Return ONLY a JSON object with this exact shape, nothing else:\n"
        '{"headline": "...", "summary": "...", "caption": "...", "hashtags": ["#a", "#b", "#c", "#d"]}\n\n'
        f"SOURCE TITLE: {titol_font}\n\n"
        f"SOURCE TEXT: {text_font[:4000]}"
    )
    missatge = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    resposta = missatge.content[0].text.strip()
    resposta = re.sub(r'^```(json)?', '', resposta).strip()
    resposta = re.sub(r'```$', '', resposta).strip()
    dades = json.loads(resposta)
    return dades


if not URL_NOTICIA and not TEXT_MANUAL:
    print("ERROR: falta URL_NOTICIA o TEXT_MANUAL")
    exit(1)

if TEXT_MANUAL:
    print("Fent servir el text manual proporcionat (sense extreure de la URL)")
    titol_font = URL_NOTICIA or "Manual"
    text_font = TEXT_MANUAL
else:
    print(f"Extraient article de: {URL_NOTICIA}")
    try:
        titol_font, text_font = extreure_article(URL_NOTICIA)
        print(f"   Titol detectat: {titol_font}")
        print(f"   Text extret: {len(text_font)} caracters")
        if len(text_font) < 200:
            print("   AVIS: molt poc text extret, la qualitat del resum pot ser baixa")
    except Exception as e:
        print(f"ERROR extraient l'article: {e}")
        exit(1)

if not ANTHROPIC_KEY:
    print("ERROR: falta ANTHROPIC_KEY")
    exit(1)

print("\nGenerant titular, resum i hashtags amb IA...")
client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
try:
    dades = generar_contingut_ia(titol_font, text_font, URL_NOTICIA, client, INSTRUCCIONS_EXTRA)
except Exception as e:
    print(f"ERROR generant contingut amb IA: {e}")
    exit(1)

headline = dades.get('headline', '').strip()
summary  = dades.get('summary', '').strip()
caption  = dades.get('caption', '').strip()
hashtags = dades.get('hashtags', [])

if not headline or not summary or len(hashtags) < 1:
    print(f"ERROR: resposta de la IA incompleta: {dades}")
    exit(1)

print(f"   Headline: {headline}")
print(f"   Summary: {summary}")
print(f"   Caption: {caption}")
print(f"   Hashtags: {' '.join(hashtags)}")

if not FOTO1_URL or not FOTO2_URL:
    print("ERROR: falten FOTO1_URL i/o FOTO2_URL (cal pujar les dues fotos des de la web app)")
    exit(1)


def descarregar_foto(url, dest_path, etiqueta):
    print(f"\nDescarregant {etiqueta}: {url}")
    try:
        r_foto = requests.get(url, timeout=60)
        r_foto.raise_for_status()
        with open(dest_path, 'wb') as f:
            f.write(r_foto.content)
        print(f"   {etiqueta} OK ({len(r_foto.content)//1024} KB)")
    except Exception as e:
        print(f"ERROR descarregant {etiqueta}: {e}")
        exit(1)


foto1_local_path = os.path.expanduser("~/foto1_noticia.jpg")
foto2_local_path = os.path.expanduser("~/foto2_noticia.jpg")
descarregar_foto(FOTO1_URL, foto1_local_path, "Foto 1 (titular)")
descarregar_foto(FOTO2_URL, foto2_local_path, "Foto 2 (resum)")

# ---------- IMATGE 1: TITULAR (Foto 1) ----------
img1 = preparar_fons(foto1_local_path, darken=0.20)
img1 = caixa_semitransparent(img1, [(0, 0), (W, BOX_TOP_H)], opacitat=0.55)
draw1 = ImageDraw.Draw(img1)

font_h, linies_h, alcada_linia_h = ajustar_bloc_text(
    draw1, headline, FONT_BEBAS,
    mides=[80, 72, 64, 56, 48, 42],
    max_width=920, max_height=BOX_TOP_H - 60
)
y_inici_h = (BOX_TOP_H - len(linies_h) * alcada_linia_h) / 2
dibuixar_bloc_centrat(draw1, linies_h, font_h, y_inici_h, alcada_linia_h, COLOR_WHITE)

img1 = afegir_logo(img1)
path1 = f"{OUTPUT}/slide1_headline.png"
img1.convert("RGB").save(path1, "PNG")
print(f"\nImatge 1 (titular) generada: {path1}")

# ---------- IMATGE 2: RESUM (Foto 2) ----------
img2 = preparar_fons(foto2_local_path, darken=0.20)
img2 = caixa_semitransparent(img2, [(0, BOX_BOT_Y), (W, H)], opacitat=0.55)
draw2 = ImageDraw.Draw(img2)

font_s, linies_s, alcada_linia_s = ajustar_bloc_text(
    draw2, summary, FONT_SEMIBOLD,
    mides=[46, 42, 38, 34, 30, 26],
    max_width=920, max_height=BOX_BOT_H - 60
)
y_inici_s = BOX_BOT_Y + (BOX_BOT_H - len(linies_s) * alcada_linia_s) / 2
dibuixar_bloc_centrat(draw2, linies_s, font_s, y_inici_s, alcada_linia_s, COLOR_WHITE)

img2 = afegir_logo(img2)
path2 = f"{OUTPUT}/slide2_summary.png"
img2.convert("RGB").save(path2, "PNG")
print(f"Imatge 2 (resum) generada: {path2}")

# ---------- DESCRIPCIO / CAPTIO ----------
descripcio = f"{caption}\n\n{' '.join(hashtags)}"
path_caption = f"{OUTPUT}/caption.txt"
with open(path_caption, 'w', encoding='utf-8') as f:
    f.write(descripcio)
print(f"Descripcio generada: {path_caption}")

print("\nTot generat correctament!")
