# torneig.py - format "BEST HARDSTYLE TRACK OF 2026": torneig d'eliminatories (versus diari, final, campio, cuadre).
# Mode (variable d'entorn DADES, JSON): versus | campio | cuadre
# Els clips de cada tema NO es baixen de YouTube: ja estan preparats al release 'torneig_clips' (torneig_preparar.py),
# amb el moment del drop detectat una sola vegada. Aixi totes les rondes reutilitzen els mateixos clips.
import os, sys, json, re, math, subprocess, wave, colorsys, io, time
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.signal import lfilter, butter
import requests
import odov_comu as OC

W, H, FPS, SR = 1080, 1920, 30, 48000
OUTPUT = os.path.expanduser("~/output"); os.makedirs(OUTPUT, exist_ok=True)
FONTS = os.path.expanduser("~/fonts")
CLIPS_DIR = os.path.expanduser("~/clips"); os.makedirs(CLIPS_DIR, exist_ok=True)
CLIPS_LOCAL = os.environ.get('TORNEIG_CLIPS_LOCAL', '')       # nomes per proves en local
REPO = os.environ.get('GITHUB_REPOSITORY', 'nilburgas-eng/onedayonevibe')
GH_TOKEN = os.environ.get('GITHUB_TOKEN', '')
TITOL_TORNEIG = "BEST HARDSTYLE TRACK OF 2026"
RONDES = ["ROUND OF 16", "QUARTER-FINALS", "SEMI-FINALS", "THE FINAL"]
RONDA_CURTA = ["R16", "QF", "SF", "F"]
NM = [8, 4, 2, 1]
ORDRE = [(r, m) for r in range(4) for m in range(NM[r])]
CYAN = (0, 229, 255); PINK = (255, 59, 107); GOLD = (255, 214, 64); ACC = [CYAN, PINK]
VIDEO_OPTS = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-profile:v', 'high', '-maxrate', '24M', '-bufsize', '48M',
              '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart']

# ============================ dades ============================
DADES = json.loads(os.environ['DADES'])
MODE = DADES.get('mode', 'versus')
TRACKS = DADES['tracks']
assert len(TRACKS) == 16, "calen exactament 16 temes"
TR = [(OC.neteja(t['nom']).strip(), OC.neteja(t['artista']).strip()) for t in TRACKS]
IDS = [t['id'] for t in TRACKS]
RES = {}
for k, v in (DADES.get('res') or {}).items():
    if v and v[0] is not None:
        a, b = k.split('-'); RES[(int(a), int(b))] = (int(v[0]), (int(v[1]) if v[1] not in (None, '') else None))
R_AVUI = int(DADES.get('ronda', 0)); M_AVUI = int(DADES.get('partit', 0))

def entrants(res):
    E = [list(range(16))]
    for r in range(4):
        E.append([res[(r, m)][0] if (r, m) in res else None for m in range(len(E[r]) // 2)])
    return E

# ============================ utilitats grafiques ============================
def _fp(n):
    p = f"{FONTS}/{n}"
    return p if os.path.exists(p) and os.path.getsize(p) > 1000 else f"{FONTS}/Montserrat-Bold.ttf"
@lru_cache(None)
def font(n, s): return ImageFont.truetype(_fp(n), int(s))
BEB = lambda s: font('BebasNeue.ttf', s)
XB = lambda s: font('Montserrat-ExtraBold.ttf', s)
SB = lambda s: font('Montserrat-SemiBold.ttf', s)
MD = lambda s: font('Montserrat-Medium.ttf', s)
def ease_out(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3
def ease_io(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
def back(x):
    x = min(max(x, 0), 1); c = 1.70158; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
def tx(d, xy, t, f, fill, anchor='la', stroke=0):
    # PIL ignora l'alfa del text sobre imatges RGB: el text amb alfa passa per una mascara
    if len(fill) == 4 and fill[3] < 255:
        a = fill[3]
        if a <= 0: return
        bb = d.textbbox(xy, t, font=f, anchor=anchor, stroke_width=stroke)
        box = (int(bb[0]) - 6, int(bb[1]) - 6, int(bb[2]) + 6, int(bb[3]) + 6)
        m = Image.new('L', (box[2] - box[0], box[3] - box[1]), 0)
        ImageDraw.Draw(m).text((xy[0] - box[0], xy[1] - box[1]), t, font=f, fill=a, anchor=anchor, stroke_width=stroke)
        d._image.paste(tuple(fill[:3]), (box[0], box[1]), m); return
    d.text(xy, t, font=f, fill=tuple(fill[:3]), anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))
def fit(d, t, fn, size, maxw, minsize=18):
    while size > minsize and d.textlength(t, font=fn(size)) > maxw: size -= 2
    return fn(size)
def short_txt(d, t, f, maxw, artist=False):
    """Retalla el text perque mai sobresurti de maxw: en llistes d'artistes treu els ultims i hi posa '+N'; si no, punts suspensius."""
    if d.textlength(t, font=f) <= maxw: return t
    if artist:
        parts = [p.strip() for p in re.split(r',|&', t) if p.strip()]
        for k in range(len(parts) - 1, 0, -1):
            c = ", ".join(parts[:k]) + f" +{len(parts) - k}"
            if d.textlength(c, font=f) <= maxw: return c
        if parts: t = parts[0]
        if d.textlength(t, font=f) <= maxw: return t
    while len(t) > 1 and d.textlength(t + "...", font=f) > maxw: t = t[:-1]
    return t.rstrip() + "..."
def fitt(d, t, fn, size, maxw, minsize=18, artist=False):
    """(text, font): redueix la mida fins a minsize i, si encara no hi cap, escurca el text."""
    f = fit(d, t, fn, size, maxw, minsize); return short_txt(d, t, f, maxw, artist), f
def make_bg():
    yy, xx = np.mgrid[0:H, 0:W]
    g = np.zeros((H, W, 3), np.float32); t = yy / H
    g[..., 0] = 14 + 10 * t; g[..., 1] = 8 + 4 * t; g[..., 2] = 30 + 22 * (1 - t)
    r = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.45) / H) ** 2)
    g *= (1.15 - 1.1 * r)[..., None].clip(0.35, 1.15)
    return Image.fromarray(g.clip(0, 255).astype(np.uint8))
BG = make_bg()
def make_cover(seed, size=700):          # portada de reserva (si no se'n troba cap)
    rng = np.random.default_rng(seed)
    h1 = rng.random(); h2 = (h1 + 0.3 + rng.random() * 0.3) % 1
    c1 = np.array(colorsys.hsv_to_rgb(h1, 0.85, 0.95)) * 255; c2 = np.array(colorsys.hsv_to_rgb(h2, 0.9, 0.5)) * 255
    y, x = np.mgrid[0:size, 0:size] / size
    ang = rng.random() * 6.28; k = (x * math.cos(ang) + y * math.sin(ang)); k = (k - k.min()) / (k.max() - k.min())
    img = (c1[None, None] * (1 - k[..., None]) + c2[None, None] * k[..., None])
    return Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert('RGBA')
_spotify = None
COVERS = {}
def carrega_portada(i):
    global _spotify
    if i in COVERS: return COVERS[i]
    if _spotify is None:
        _spotify = OC.spotify_token(os.environ.get('SPOTIFY_CLIENT_ID', ''), os.environ.get('SPOTIFY_CLIENT_SECRET', '')) or False
    img = None
    try:
        dades, font_ = OC.obtenir_portada(TR[i][0], TR[i][1], _spotify or None)
        if dades:
            im = Image.open(io.BytesIO(dades)).convert('RGBA'); s = min(im.size)
            img = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2)).resize((700, 700), Image.LANCZOS)
            print(f"   Portada {TR[i][0]}: {font_}")
    except Exception as e:
        print(f"   Portada {TR[i][0]}: error {e}")
    if img is None:
        print(f"   AVIS: sense portada per '{TR[i][0]}' (es fa servir una de reserva)"); img = make_cover(i + 3)
    COVERS[i] = img; return img
@lru_cache(None)
def cover(i, size, rad=36):
    im = carrega_portada(i).resize((size, size), Image.LANCZOS)
    m = Image.new('L', (size * 2, size * 2), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, size * 2 - 1, size * 2 - 1), rad * 2, fill=255)
    im.putalpha(m.resize((size, size), Image.LANCZOS)); return im
@lru_cache(None)
def glow(color, size, spread=120, alpha=150):
    im = Image.new('RGBA', (size + 2 * spread, size + 2 * spread), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((spread, spread, spread + size, spread + size), 40, fill=color + (alpha,))
    return im.filter(ImageFilter.GaussianBlur(spread / 2.2))
def fade(im, k):
    if k >= 0.999: return im
    im = im.copy(); im.putalpha(im.getchannel('A').point(lambda v: int(v * max(k, 0)))); return im
LOGO = Image.open('logo.png').convert('RGBA') if os.path.exists('logo.png') else None
if LOGO is not None: LOGO = LOGO.resize((120, int(LOGO.height * 120 / LOGO.width)), Image.LANCZOS)
def logo(img):
    if LOGO is not None: img.paste(LOGO, (540 - 60, 1488 - LOGO.height // 2), LOGO)
def overlay(img, ov): img.paste(ov, (0, 0), ov)
def rays(img, t, cx, cy, color, alpha=30, n=16, speed=0.12, width=0.11):
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov); L = 2400
    for i in range(n):
        a = t * speed + i * 2 * math.pi / n
        d.polygon([(cx, cy), (cx + L * math.cos(a - width / 2), cy + L * math.sin(a - width / 2)), (cx + L * math.cos(a + width / 2), cy + L * math.sin(a + width / 2))], fill=color + (alpha,))
    overlay(img, ov)
PART = np.random.default_rng(8).random((70, 5))
def particles(img, t, color=GOLD, alpha=130):
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for x0, y0, sp, sz, ph in PART:
        y = (y0 * H - t * (40 + 120 * sp)) % H; x = x0 * W + 18 * math.sin(t * 1.3 + ph * 6)
        r = 2 + 4 * sz; a = int(alpha * (0.5 + 0.5 * math.sin(t * 2 + ph * 9)))
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (a,))
    overlay(img, ov)
def glow_text(img, xy, text, f, color, blur=18, strength=0.8, anchor='mm', core=None):
    pad = 80; d0 = ImageDraw.Draw(img); bb = d0.textbbox(xy, text, font=f, anchor=anchor)
    box = (int(bb[0]) - pad, int(bb[1]) - pad, int(bb[2]) + pad, int(bb[3]) + pad)
    m = Image.new('L', (box[2] - box[0], box[3] - box[1]), 0)
    ImageDraw.Draw(m).text((xy[0] - box[0], xy[1] - box[1]), text, font=f, fill=255, anchor=anchor)
    g = m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(min(255, v * strength * 2)))
    img.paste(color, (box[0], box[1]), g); img.paste(core if core else color, (box[0], box[1]), m)
def gt(img, xy, text, size, al=1.0, blur=22):
    glow_text(img, xy, text, BEB(size), tuple(int(c * al) for c in GOLD), blur, 0.5 * al, core=tuple(int(c * al) for c in (255, 238, 170)))
def badge(d, cx, cy, r, letter, acc, s=1.0):
    r = int(r * s)
    if r < 2: return
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=acc + (255,), outline=(255, 255, 255, 255), width=max(2, int(5 * s)))
    tx(d, (cx, cy + int(4 * s)), letter, BEB(int(r * 1.35)), (10, 10, 24), 'mm')
def vs_badge(d, cx, cy, r, s, gold=False):
    if s <= 0.02: return
    rr = int(r * s)
    d.ellipse((cx - rr - 8, cy - rr - 8, cx + rr + 8, cy + rr + 8), outline=(GOLD + (200,)) if gold else (255, 255, 255, 90), width=4)
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(255, 255, 255, 255))
    tx(d, (cx, cy + int(3 * s)), "VS", BEB(int(rr * 1.15)), (12, 12, 28), 'mm')
def title_block(d, idx, cx, ytitle, yart, maxw, tsize, asize, acc, alpha=255):
    n, a = TR[idx]
    n2, fn_ = fitt(d, n, BEB, tsize, maxw, artist=True); tx(d, (cx, ytitle), n2, fn_, (255, 255, 255, alpha), 'mm')
    a2, fa_ = fitt(d, a, SB, asize, maxw); tx(d, (cx, yart), a2, fa_, acc + (alpha,), 'mm')
def crown(d, cx, by, s=1.0, alpha=255):
    P = [(-100, 0), (-112, -84), (-56, -42), (0, -104), (56, -42), (112, -84), (100, 0)]
    d.polygon([(cx + x * s, by + y * s) for x, y in P], fill=GOLD + (alpha,), outline=(255, 255, 255, alpha))
    for x, y in ((-112, -84), (0, -104), (112, -84)):
        d.ellipse((cx + (x - 12) * s, by + (y - 12) * s, cx + (x + 12) * s, by + (y + 12) * s), fill=(255, 255, 255, alpha))
    d.rectangle((cx - 100 * s, by + 6 * s, cx + 100 * s, by + 22 * s), fill=GOLD + (alpha,))

# ============================ cuadre ============================
C0, C1, C2, C3 = (55, 290), (359, 190), (563, 170), (747, 130)
COLS = [C0, C1, C2, C3]; BH, PITCH = 58, 64
def bracket_full(res, today=None, sub="", video=True):
    img = BG.copy(); d = ImageDraw.Draw(img, 'RGBA'); E = entrants(res); meta = {}
    tx(d, (540, 282), TITOL_TORNEIG, fit(d, TITOL_TORNEIG, BEB, 70, 900), (255, 255, 255), 'mm')
    tx(d, (540, 338), sub, SB(28), GOLD, 'mm')
    def box(x, y, w, idx, pct, state, acc=None, label=None, small=False):
        fill = {'win': (0, 229, 255, 34), 'lose': (255, 255, 255, 8), 'tbd': (255, 255, 255, 12), 'norm': (255, 255, 255, 20)}[state]
        out = {'win': CYAN + (230,), 'lose': (255, 255, 255, 26), 'tbd': (255, 255, 255, 36), 'norm': (255, 255, 255, 48)}[state]
        if acc: out = acc + (255,)
        d.rounded_rectangle((x, y, x + w, y + BH), 12, fill=fill, outline=out, width=3 if (acc or state == 'win') else 2)
        if label:
            tx(d, (x + w // 2, y + BH // 2), label, XB(18), (255, 255, 255), 'mm'); return
        if idx is None:
            tx(d, (x + 14, y + BH // 2), "TBD", MD(22), (84, 84, 104), 'lm'); return
        name, art = TR[idx]; dim = state == 'lose'
        tc = (96, 96, 116) if dim else (255, 255, 255); ac = (80, 80, 98) if dim else (190, 200, 215)
        mw = w - 26 - (54 if (pct is not None and not small) else 0)
        mw_art = mw - (48 if (pct is not None and small) else 0)      # a les columnes estretes el % va a la linia del titol
        nm2, fn1 = fitt(d, name, SB, 24, mw, 14, artist=True); ar2, fn2 = fitt(d, art, MD, 15, mw_art, 11)
        tx(d, (x + 14, y + 19), nm2, fn1, tc, 'lm'); tx(d, (x + 14, y + 42), ar2, fn2, ac, 'lm')
        if pct is not None and not small:
            tx(d, (x + w - 12, y + BH // 2), f"{pct}%", XB(22) if state == 'win' else MD(20), CYAN if state == 'win' else (96, 96, 116), 'rm')
        elif pct is not None:
            tx(d, (x + w - 12, y + 42), f"{pct}%", XB(16) if state == 'win' else MD(15), CYAN if state == 'win' else (96, 96, 116), 'rm')
    def line(p, q): d.line([p, q], fill=(255, 255, 255, 64), width=3)
    def half(y0, h):
        ys = [[y0 + i * PITCH for i in range(8)]]
        for lvl in range(1, 4):
            prev = ys[-1]; ys.append([(prev[2 * j] + prev[2 * j + 1]) / 2 for j in range(len(prev) // 2)])
        for r in range(4):
            n = 8 >> r
            for k in range(n):
                ei = h * n + k; idx = E[r][ei]; m = ei // 2; st = 'norm'; pct = None; acc = None; label = None
                if idx is None: st = 'tbd'
                elif (r, m) in res:
                    w, p = res[(r, m)]
                    if idx == w: st, pct = 'win', p
                    else: st, pct = 'lose', (None if p is None else 100 - p)
                elif today == (r, m): acc = ACC[ei % 2]
                if idx is None and r > 0 and today == (r - 1, ei): label = "PLAYING TODAY"
                x, w_ = COLS[r]
                box(x, ys[r][k], w_, idx, None if r == 3 else pct, st, acc, label, small=(r >= 2))
                meta[('box', r, ei)] = (x, ys[r][k], x + w_, ys[r][k] + BH)
        for lvl in range(3):
            a = COLS[lvl]; b = COLS[lvl + 1]; xm = (a[0] + a[1] + b[0]) // 2
            for j in range(len(ys[lvl + 1])):
                p = ys[lvl][2 * j] + BH / 2; q = ys[lvl][2 * j + 1] + BH / 2; rr = ys[lvl + 1][j] + BH / 2
                line((a[0] + a[1], p), (xm, p)); line((a[0] + a[1], q), (xm, q)); line((xm, p), (xm, q)); line((xm, rr), (b[0], rr))
        return ys[3][0] + BH / 2
    for x, l in ((C0[0] + C0[1] // 2, "ROUND OF 16"), (C1[0] + C1[1] // 2, "QUARTERS"), (C2[0] + C2[1] // 2, "SEMIS"), (C3[0] + C3[1] // 2, "FINALISTS")):
        tx(d, (x, 372), l, SB(16), (255, 255, 255, 110), 'mm')
    cy1 = half(392, 0); cy2 = half(1052, 1)
    fy = (cy1 + cy2) / 2; xj = C3[0] + C3[1] + 18
    for cy in (cy1, cy2): line((C3[0] + C3[1], cy), (xj, cy))
    line((xj, cy1), (xj, cy2)); line((740, fy), (xj, fy))
    bf = (170, fy - 44, 740, fy + 44); meta['final'] = bf
    if (3, 0) in res:
        w, p = res[(3, 0)]
        d.rounded_rectangle(bf, 16, fill=(255, 214, 64, 60), outline=GOLD + (255,), width=4)
        tx(d, (455, fy - 16), "CHAMPION", BEB(30), GOLD, 'mm')
        cw, cf = fitt(d, TR[w][0], XB, 30, 520, 16, artist=True); tx(d, (455, fy + 16), cw, cf, (255, 255, 255), 'mm')
    else:
        d.rounded_rectangle(bf, 16, fill=(255, 214, 64, 28), outline=GOLD + (255,), width=3)
        tx(d, (455, fy - 12), "THE FINAL", BEB(52), GOLD, 'mm')
        tx(d, (455, fy + 26), "winner = best hardstyle track of 2026", MD(19), (255, 255, 255, 200), 'mm')
    if not video:
        tx(d, (540, 1640), "@onedayonevibe  ·  one versus every day  ·  you decide", MD(24), (255, 255, 255, 150), 'mm')
        if LOGO is not None: img.paste(LOGO, (540 - 60, 1700), LOGO)
    return img, meta

# ============================ so (efectes sintetics) ============================
rng = np.random.default_rng(33)
def lpf(x, fc): b, a = butter(2, fc / (SR / 2), 'low'); return lfilter(b, a, x)
def hpf(x, fc): b, a = butter(2, fc / (SR / 2), 'high'); return lfilter(b, a, x)
def saw(f, dur, det=(0.994, 1.0, 1.006)):
    t = np.arange(int(SR * dur)) / SR; return sum(2 * ((t * f * d) % 1.0) - 1 for d in det) / len(det)
def whoosh(d, up=True):
    n = int(SR * d); x = rng.standard_normal(n); out = np.zeros(n); seg = max(1, n // 12)
    for k in range(12):
        fc = 300 + (k / 11 if up else 1 - k / 11) * 5000; out[k * seg:(k + 1) * seg] = lpf(x[k * seg:(k + 1) * seg], fc)
    return out * np.sin(np.pi * np.linspace(0, 1, n)) ** 2 * 0.5
def thump(len_=0.5, decay=7):
    t = np.arange(int(SR * len_)) / SR; f = 40 + 120 * np.exp(-t * 22); s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * decay)
    return np.tanh(2 * s) + 0.2 * hpf(rng.standard_normal(len(t)), 2500) * np.exp(-t * 60)
def riser(d):
    n = int(SR * d); t = np.arange(n) / SR; x = rng.standard_normal(n); out = np.zeros(n); seg = n // 40
    for k in range(40):
        fc = 200 + (k / 39) ** 2 * 7000; out[k * seg:(k + 1) * seg] = lpf(x[k * seg:(k + 1) * seg], fc)
    f = 80 + 900 * (t / d) ** 2; tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return (out * 0.6 + tone * 0.35) * (t / d) ** 1.6
def boom(d=2.5):
    n = int(SR * d); t = np.arange(n) / SR; sub = thump(1.2, 3.0); out = np.zeros(n); out[:len(sub)] += sub * 1.1
    return out + hpf(rng.standard_normal(n), 3000) * np.exp(-t * 2.2) * 0.5
def chord(freqs, d, att=0.05, rel=1.2, g=0.12):
    n = int(SR * d); t = np.arange(n) / SR; s = sum(lpf(saw(f, d), 3500) for f in freqs) / len(freqs)
    return s * np.minimum(1, t / att) * np.exp(-np.maximum(0, t - (d - rel)) * 3) * g
class Mix:
    def __init__(self, total): self.A = np.zeros((int(total * SR) + SR, 2), np.float64); self.total = total
    def mono(self, s, t0, g=1.0):
        i = int(t0 * SR); s = s[:max(0, len(self.A) - i)]; self.A[i:i + len(s), 0] += s * g; self.A[i:i + len(s), 1] += s * g
    def stereo(self, s, t0, g=1.0):
        i = int(t0 * SR); s = s[:max(0, len(self.A) - i)]; self.A[i:i + len(s)] += s * g
    def save(self, name):
        A = self.A[:int(self.total * SR)]; pk = np.max(np.abs(A)) + 1e-9
        if pk > 0.97: A = A * (0.97 / pk)
        with wave.open(name, 'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((A * 32767).astype(np.int16).tobytes())

# ============================ clips reals (release torneig_clips) ============================
_assexs = None
def ensure_clip(i):
    nom = f"clip_{IDS[i]}.mp4"
    if CLIPS_LOCAL:
        p = os.path.join(CLIPS_LOCAL, nom); return p if os.path.exists(p) else None
    p = os.path.join(CLIPS_DIR, nom)
    if os.path.exists(p) and os.path.getsize(p) > 10000: return p
    global _assexs
    if _assexs is None:
        _assexs = {}
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/torneig_clips", headers={"Authorization": f"token {GH_TOKEN}"})
        if r.status_code == 200:
            for a in r.json().get('assets', []): _assexs[a['name']] = a['url']
        else:
            print(f"AVIS: no s'ha pogut llegir el release torneig_clips ({r.status_code})")
    url = _assexs.get(nom)
    if not url: return None
    r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/octet-stream"}, stream=True)
    if r.status_code != 200: return None
    with open(p, 'wb') as f:
        for ch in r.iter_content(1 << 20): f.write(ch)
    return p
VF_FONS = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},gblur=sigma=9:steps=2,lutrgb=r='val*0.5':g='val*0.5':b='val*0.5'"
class Clip:
    """Un tema del torneig: video de fons (difuminat i enfosquit), so, espectre i pulsacions reals."""
    def __init__(self, i, dur):
        self.i = i; self.dur = dur; self.path = ensure_clip(i); self.reader = None; self.last = None
        self.n = int(dur * FPS)
        if self.path:
            p = subprocess.run(['ffmpeg', '-v', 'error', '-i', self.path, '-t', str(dur), '-vn', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'], capture_output=True)
            a = np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64)
        else:
            print(f"AVIS: no hi ha clip preparat per '{TR[i][0]}' (fons amb la portada difuminada i sense so). Fes 'Preparar clips'.")
            a = np.zeros((0, 2))
        need = int(dur * SR)
        self.audio = a[:need] if len(a) >= need else np.vstack([a, np.zeros((need - len(a), 2))])
        self.mono = self.audio.mean(axis=1)
        self.eq = self._eq(); self.beats = self._beats()
        self.fallback = None
    def _eq(self):
        NB = 36; bands = np.geomspace(50, 9000, NB); sn = self.mono
        def raw(tl):
            c = int(tl * SR); seg = sn[max(0, c - 1024):c + 1024]
            if len(seg) < 2048: seg = np.pad(seg, (0, 2048 - len(seg)))
            sp = np.abs(np.fft.rfft(seg * np.hanning(2048))); fr = np.fft.rfftfreq(2048, 1 / SR); out = []
            for b in range(NB):
                m = (fr >= bands[b] / 1.1) & (fr < bands[b] * 1.1); out.append(sp[m].mean() if m.any() else 0)
            return np.array(out)
        r = np.array([raw(k / FPS) for k in range(self.n)]); ref = np.percentile(r, 92, axis=0) + 1e-9
        v = np.clip(r / ref, 0, 1.15) ** 0.8; sm = np.zeros_like(v)
        for k in range(len(v)): sm[k] = np.maximum(v[k], sm[k - 1] * 0.78) if k else v[k]
        return np.clip(sm, 0, 1)
    def _beats(self):
        try:
            import librosa
            y = librosa.resample(self.mono.astype(np.float32), orig_sr=SR, target_sr=22050)
            tempo, b = librosa.beat.beat_track(y=y, sr=22050)
            bt = librosa.frames_to_time(b, sr=22050)
            if len(bt) >= 4: return np.array(bt)
        except Exception as e:
            print(f"   (pulsacions per defecte: {e})")
        return np.arange(0, self.dur, 60 / 150)
    def pulse(self, tl):
        prev = self.beats[self.beats <= tl]
        return math.exp(-(tl - (prev[-1] if len(prev) else 0)) * 5)
    def eq_at(self, tl): return self.eq[min(int(tl * FPS), len(self.eq) - 1)]
    def read(self):
        """Seguent fotograma del fons (en ordre)."""
        if self.path:
            if self.reader is None:
                self.reader = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', self.path, '-t', str(self.dur), '-vf', VF_FONS, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            sz = W * H * 3; buf = b''
            while len(buf) < sz:
                ch = self.reader.stdout.read(sz - len(buf))
                if not ch: break
                buf += ch
            if len(buf) == sz: self.last = Image.frombytes('RGB', (W, H), buf)
            if self.last is not None: return self.last.copy()
        if self.fallback is None:
            bgf = carrega_portada(self.i).convert('RGB').resize((H, H)).crop(((H - W) // 2, 0, (H + W) // 2, H)).filter(ImageFilter.GaussianBlur(40))
            self.fallback = Image.eval(bgf, lambda v: int(v * 0.4))
        return self.fallback.copy()

# ============================ escenes: versus / final ============================
def header(d, t=99):
    a = int(255 * ease_out(t / 0.6)); y = 282 - int(24 * (1 - ease_out(t / 0.6)))
    if EPIC:
        tx(d, (540, 282), "THE FINAL", BEB(66), GOLD, 'mm'); tx(d, (540, 336), TITOL_TORNEIG, SB(26), (255, 255, 255), 'mm'); return
    tx(d, (540, y), TITOL_TORNEIG, fit(d, TITOL_TORNEIG, BEB, 66, 900), (255, 255, 255, a), 'mm')
    tx(d, (540, y + 54), SUBTXT, SB(28), CYAN + (a,), 'mm')
def f_intro(t):
    return f_intro_epic(t) if EPIC else f_intro_norm(t)
def f_intro_norm(t):
    img = BG.copy(); d = ImageDraw.Draw(img, 'RGBA'); header(d, t)
    for k, (idx, cx) in enumerate(((FA, 300), (FB, 760))):
        e = ease_out((t - 0.35 - 0.12 * k) / 0.55); dx = (1 - e) * (-520 if k == 0 else 520)
        g = fade(glow(ACC[k], 380, 100, 110), e); img.paste(g, (int(cx - 190 - 100 + dx), 560 - 100), g)
        c = fade(cover(idx, 380), e); img.paste(c, (int(cx - 190 + dx), 560), c)
        badge(d, int(cx - 190 + dx) + 8, 568, 46, "AB"[k], ACC[k], back((t - 0.7 - 0.1 * k) / 0.35))
        title_block(d, idx, cx, 985, 1040, 290, 52, 26, ACC[k], int(255 * ease_out((t - 0.9) / 0.4)))
    vs_badge(d, 530, 750, 50, back((t - 1.0) / 0.35))
    if 1.0 < t < 1.5:
        r = int(60 + 240 * (t - 1.0) / 0.5); a = int(160 * (1 - (t - 1.0) / 0.5)); d.ellipse((530 - r, 750 - r, 530 + r, 750 + r), outline=(255, 255, 255, a), width=4)
    al = ease_out((t - 1.6) / 0.5)
    if al > 0:
        y = int(1180 + 20 * (1 - al)); w = 700
        if PREV:
            d.rounded_rectangle((540 - w // 2, y - 36, 540 + w // 2, y + 36), 36, fill=(255, 255, 255, int(24 * al)), outline=(255, 255, 255, int(70 * al)), width=2)
            pre, suf = "YESTERDAY  ·  ", " advanced" + (f"  ({PREV[1]}%)" if PREV[1] is not None else "")
            fpv = SB(26); room = w - 60 - d.textlength(pre + suf, font=fpv)
            txt = pre + short_txt(d, TR[PREV[0]][0], fpv, room, artist=True) + suf
            tx(d, (540, y), txt, fpv, (255, 255, 255, int(255 * al)), 'mm'); yy = y + 90
        else: yy = y
        tx(d, (540, yy), "ONE VERSUS EVERY DAY  ·  YOU DECIDE", SB(30), CYAN + (int(255 * al),), 'mm')
    logo(img); return img
def cami(idx):
    out = []
    for rr in range(3):
        ei = E_VIEW[rr].index(idx) if idx in E_VIEW[rr] else None
        if ei is None or (rr, ei // 2) not in RES_VIEW: break
        w, p = RES_VIEW[(rr, ei // 2)]; opp = E_VIEW[rr][ei ^ 1]
        out.append((RONDA_CURTA[rr], opp, p))
    return out
def f_intro_epic(t):
    img = BG.copy(); rays(img, t, 540, 780, GOLD, int(22 * min(1, t / 1.0))); particles(img, t)
    d = ImageDraw.Draw(img, 'RGBA')
    if t < 1.2:
        a = int(255 * ease_out((t - 0.2) / 0.4) * (1 - ease_out((t - 1.0) / 0.2)))
        tx(d, (540, 780), "ONE LAST VERSUS", SB(44), (255, 255, 255, a), 'mm')
    else:
        ts = (t - 1.2) / 0.35; sc = 1 + 0.8 * (1 - ease_out(ts)); al = ease_out(ts * 1.5)
        sh = (1 - min(1, (t - 1.2) / 0.5)) if t < 1.7 else 0
        dx = int(12 * math.sin(t * 90) * sh); dy = int(8 * math.cos(t * 70) * sh)
        glow_text(img, (540 + dx, 380 + dy), "THE FINAL", BEB(int(250 * sc)), tuple(int(c * al) for c in GOLD), 26, 0.55 * al, core=tuple(int(c * al) for c in (255, 238, 170)))
        tx(d, (540, 500), TITOL_TORNEIG, SB(34), (255, 255, 255, int(255 * ease_out((t - 1.8) / 0.5))), 'mm')
    for k, (idx, cx) in enumerate(((FA, 300), (FB, 760))):
        e = ease_out((t - 2.0 - 0.15 * k) / 0.6); dx = (1 - e) * (-560 if k == 0 else 560)
        if e > 0:
            g = fade(glow(ACC[k], 380, 100, 120), e); img.paste(g, (int(cx - 190 - 100 + dx), 600 - 100), g)
            c = fade(cover(idx, 380), e); img.paste(c, (int(cx - 190 + dx), 600), c)
            badge(d, int(cx - 190 + dx) + 8, 608, 46, "AB"[k], ACC[k], back((t - 2.6 - 0.1 * k) / 0.35))
            title_block(d, idx, cx, 1018, 1070, 290, 50, 26, ACC[k], int(255 * ease_out((t - 2.7) / 0.4)))
    vs_badge(d, 530, 790, 50, back((t - 3.0) / 0.35), True)
    if 3.0 < t < 3.6:
        r = int(60 + 300 * (t - 3.0) / 0.6); a = int(200 * (1 - (t - 3.0) / 0.6)); d.ellipse((530 - r, 790 - r, 530 + r, 790 + r), outline=GOLD + (a,), width=5)
    ep = ease_out((t - 3.5) / 0.4)
    tx(d, (540, 1135), "ROAD TO THE FINAL", SB(22), GOLD + (int(255 * ep),), 'mm')
    for k, (idx, cx) in enumerate(((FA, 300), (FB, 760))):
        for i, (rl, opp, pc) in enumerate(cami(idx)):
            a = int(255 * ease_out((t - 3.8 - 0.3 * i) / 0.35))
            fpv = MD(22); pre, suf = f"{rl}  ·  ", (f"  {pc}%" if pc is not None else "")
            s = pre + short_txt(d, TR[opp][0], fpv, 290 - d.textlength(pre + suf, font=fpv), artist=True) + suf
            tx(d, (cx, 1182 + i * 42), s, fpv, (255, 255, 255, a), 'mm')
    ef = ease_out((t - 4.8) / 0.5)
    if ef > 0: tx(d, (540, 1360), "TWO TRACKS. ONE CHAMPION.", fit(d, "TWO TRACKS. ONE CHAMPION.", BEB, 72, 820), GOLD + (int(255 * ef),), 'mm')
    logo(img); return img
def f_track(k, tl):
    clip = CLIPS[k]; idx = (FA, FB)[k]; oth = (FB, FA)[k]; acc = ACC[k]
    img = clip.read()
    if EPIC: rays(img, tl, 540, 700, acc, 10); particles(img, tl, GOLD, 90)
    d = ImageDraw.Draw(img, 'RGBA')
    e_in = ease_out(tl / 0.5); e_out = ease_io((tl - (CLIP - 0.35)) / 0.35)
    dx = (-1 if k == 0 else 1) * 720 * ((1 - e_in) + e_out); al = e_in * (1 - e_out)
    pulse = 1 + (0.03 if EPIC else 0.028) * clip.pulse(tl)
    sz = int(600 * pulse); cx = 540; cy = 700
    g = fade(glow(acc, 600, 120, 170 if EPIC else 150), al); img.paste(g, (int(240 - 120 + dx), 400 - 120), g)
    c = fade(cover(idx, sz), al); x0 = int(cx - sz / 2 + dx); y0 = int(cy - sz / 2); img.paste(c, (x0, y0), c)
    if EPIC: d.rounded_rectangle((x0 - 6, y0 - 6, x0 + sz + 6, y0 + sz + 6), 44, outline=GOLD + (int(230 * al),), width=4)
    header(d)
    badge(d, int(240 + dx) + 6, 408, 56, "AB"[k], acc, 1.0)
    a = int(255 * al)
    title_block(d, idx, int(540 + dx), 1050, 1126, 720, 96, 40, acc, a)
    tx(d, (int(540 + dx), 1190), f"vs  {TR[oth][0]}  ·  {TR[oth][1]}", MD(26), (255, 255, 255, int(150 * al)), 'mm')
    bars = clip.eq_at(tl)
    for i in range(36):
        h = int(8 + 130 * bars[i]); x = 170 + i * 20
        d.rounded_rectangle((x, 1390 - h, x + 13, 1390), 5, fill=acc + (int(235 * al),))
    p = min(1, tl / CLIP); d.rounded_rectangle((170, 1420, 890, 1428), 4, fill=(255, 255, 255, 40)); d.rounded_rectangle((170, 1420, 170 + int(720 * p), 1428), 4, fill=acc + (255,))
    tx(d, (890, 1452), f"0:{int(max(0, CLIP - tl)):02d}", MD(22), (255, 255, 255, 150), 'rm')
    logo(img); return img
def f_bracket(tl):
    e = ease_out(tl / 0.4); xo = ease_io((tl - (BRK - 0.3)) / 0.3)
    img = Image.blend(BG, BRK_IMG, e * (1 - xo)); d = ImageDraw.Draw(img, 'RGBA')
    pu = 0.55 + 0.45 * math.sin(tl * 7); a = int(255 * pu * e * (1 - xo))
    for h in range(2):
        key = ('box', R_AVUI, 2 * M_AVUI + h)
        if key in META_BRK:
            x0, y0, x1, y1 = META_BRK[key]; d.rounded_rectangle((x0 - 5, y0 - 5, x1 + 5, y1 + 5), 14, outline=ACC[h] + (a,), width=5)
    if R_AVUI < 3:
        key = ('box', R_AVUI + 1, M_AVUI)
        if key in META_BRK:
            x0, y0, x1, y1 = META_BRK[key]; d.rounded_rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), 14, outline=(255, 255, 255, a), width=4)
    else:
        x0, y0, x1, y1 = META_BRK['final']; d.rounded_rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), 20, outline=(255, 255, 255, a), width=4)
    return img
def f_vote(tl):
    img = BG.copy()
    if EPIC: rays(img, tl, 540, 780, GOLD, 16); particles(img, tl)
    d = ImageDraw.Draw(img, 'RGBA'); header(d)
    for k, (idx, cx) in enumerate(((FA, 300), (FB, 760))):
        ek = ease_out((tl - 0.15 - 0.1 * k) / 0.45)
        g = fade(glow(ACC[k], 380, 100, 130 if EPIC else 120), ek); img.paste(g, (cx - 190 - 100, 560 - 100 + int(20 * (1 - ek))), g)
        c = fade(cover(idx, 380), ek); img.paste(c, (cx - 190, 560 + int(20 * (1 - ek))), c)
        badge(d, cx - 190 + 8, 568, 46, "AB"[k], ACC[k], back((tl - 0.4 - 0.1 * k) / 0.3))
        title_block(d, idx, cx, 980, 1032, 280, 46, 24, ACC[k], int(255 * ek))
    vs_badge(d, 530, 750, 46, back((tl - 0.5) / 0.3), EPIC)
    e = ease_out(tl / 0.4); s = back(tl / 0.4); ep = ease_out((tl - 0.9) / 0.4)
    if EPIC:
        sc = 1 + 0.6 * (1 - ease_out(tl / 0.35)); gt(img, (540, 470), "THE LAST VOTE", int(140 * sc), ease_out(tl / 0.35), 20)
        tx(d, (540, 1112), "ONE VOTE.  ONE CHAMPION.", SB(34), CYAN + (int(255 * ep),), 'mm')
        pp = ease_out((tl - 1.5) / 0.5)
        tx(d, (540, 1352), "VOTING CLOSES IN 24 HOURS", SB(30), GOLD + (int(255 * pp),), 'mm')
        tx(d, (540, 1402), "THE CHAMPION IS REVEALED SOON", SB(21), (255, 255, 255, int(150 * pp)), 'mm')
    else:
        tx(d, (540, 470), "WHO WINS?", BEB(int(150 * max(s, 0.01))), (255, 255, 255, int(255 * e)), 'mm')
        tx(d, (540, 1112), "VOTE IN THE POLL", SB(36), CYAN + (int(255 * ep),), 'mm')
        pp = ease_out((tl - 1.4) / 0.5)
        tx(d, (540, 1336), f"{RONDES[R_AVUI]}  ·  MATCH {M_AVUI + 1} / {NM[R_AVUI]}", SB(22), (255, 255, 255, int(170 * pp)), 'mm')
        n = NM[R_AVUI]; x_ini = int(540 - (n * 80 - 10) / 2)
        for m in range(n):
            x = x_ini + m * 80; col = (255, 255, 255, int(50 * pp))
            if (R_AVUI, m) in RES_VIEW or m < M_AVUI: col = CYAN + (int(255 * pp),)
            elif m == M_AVUI: col = (255, 255, 255, int(255 * pp * (0.6 + 0.4 * math.sin(tl * 5))))
            d.rounded_rectangle((x, 1364, x + 70, 1378), 7, fill=col)
        sig = ("QUARTERS", "SEMIS", "FINAL")[R_AVUI]
        tx(d, (540, 1412), f"RESULT TOMORROW  ·  WINNER GOES TO THE {sig}", SB(21), (255, 255, 255, int(150 * pp)), 'mm')
    logo(img); return img
def frame_versus(fi):
    t = fi / FPS
    if t < T_A: return f_intro(t)
    if t < T_B: return f_track(0, t - T_A)
    if t < T_BR: return f_track(1, t - T_B)
    if t < T_V: return f_bracket(t - T_BR)
    return f_vote(t - T_V)

# ============================ escenes: campio ============================
STICK = Image.open('sticker_playlist.png').convert('RGBA') if os.path.exists('sticker_playlist.png') else None
if STICK is not None: STICK = STICK.resize((620, int(STICK.height * 620 / STICK.width)), Image.LANCZOS)
cr = np.random.default_rng(5); NC = 170
CXX = cr.random(NC) * W; CYY = -cr.random(NC) * H * 1.3; CV = 300 + cr.random(NC) * 420; CPH = cr.random(NC) * 6.28
CW = 10 + cr.random(NC) * 14; CHH = 6 + cr.random(NC) * 8; CR = 1 + cr.random(NC) * 5
CCOL = [GOLD, CYAN, PINK, (255, 255, 255), (255, 160, 40)]
def confetti(img, t, t0, k=1.0):
    d = ImageDraw.Draw(img); tt = t - t0
    if tt < 0: return
    for i in range(int(NC * k)):
        y = CYY[i] + CV[i] * tt
        if y > H + 40 or y < -40: continue
        x = CXX[i] + 45 * math.sin(tt * 2.2 + CPH[i]); a = CR[i] * tt + CPH[i]; ca, sa = math.cos(a), math.sin(a)
        sq = 0.35 + 0.65 * abs(math.sin(tt * 3 + CPH[i])); w2, h2 = CW[i] / 2, CHH[i] / 2 * sq
        d.polygon([(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in ((-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2))], fill=CCOL[i % len(CCOL)])
def c_head(d, sub, subcol=GOLD):
    tx(d, (540, 282), TITOL_TORNEIG, fit(d, TITOL_TORNEIG, BEB, 66, 900), (255, 255, 255), 'mm'); tx(d, (540, 336), sub, SB(28), subcol, 'mm')
def f_c1(t):
    img = BG.copy(); rays(img, t, 540, 800, GOLD, int(8 + 22 * min(1, t / 3.5)), speed=0.05 + 0.03 * t); particles(img, t)
    d = ImageDraw.Draw(img, 'RGBA'); tx(d, (540, 282), TITOL_TORNEIG, fit(d, TITOL_TORNEIG, BEB, 66, 900), (255, 255, 255), 'mm')
    for txt, t0, y, col, sz in (("15 VERSUS", 0.3, 560, (255, 255, 255), 120), ("16 TRACKS", 0.9, 710, (255, 255, 255), 120), ("ONE CHAMPION", 1.5, 860, GOLD, 120)):
        a = int(255 * ease_out((t - t0) / 0.3)); yy = y + int(24 * (1 - ease_out((t - t0) / 0.3)))
        tx(d, (540, yy), txt, BEB(sz), col + (a,), 'mm')
    a = ease_out((t - 2.4) / 0.4) * (0.75 + 0.25 * math.sin(t * 10))
    tx(d, (540, 1130), "AND THE WINNER IS...", BEB(100), (255, 255, 255, int(255 * a)), 'mm')
    for tt in (1.5, 2.0, 2.45, 2.8, 3.1, 3.3):
        if 0 < t - tt < 0.5:
            r = int(40 + 180 * (t - tt) / 0.5); al = int(150 * (1 - (t - tt) / 0.5)); d.ellipse((540 - r, 1300 - r, 540 + r, 1300 + r), outline=GOLD + (al,), width=4)
    logo(img); return img
def f_c2(tl):
    img = BG.copy(); rays(img, tl, 540, 760, GOLD, 18); particles(img, tl)
    d = ImageDraw.Draw(img, 'RGBA'); c_head(d, "THE FINAL RESULT")
    prog = ease_io((tl - 0.6) / 2.6)
    for k, (idx, cx) in enumerate(((CH, 270), (RU, 810))):
        e = ease_out((tl - 0.1 * k) / 0.5); dx = (1 - e) * (-400 if k == 0 else 400)
        g = fade(glow(ACC[k], 300, 90, 120), e); img.paste(g, (int(cx - 150 - 90 + dx), 480 - 90), g)
        c = fade(cover(idx, 300, 30), e); img.paste(c, (int(cx - 150 + dx), 480), c)
        title_block(d, idx, cx, 845, 892, 300, 46, 24, ACC[k], int(255 * e))
        tx(d, (cx - (20 if k else 0), 1020), f"{int(round(PCT[k] * prog))}%", BEB(150), ACC[k], 'mm')
    x0, x1, y0, y1 = 170, 890, 1130, 1190
    d.rounded_rectangle((x0, y0, x1, y1), 30, fill=(255, 255, 255, 26))
    wA = int(720 * PCT[0] / 100 * prog); wB = int(720 * PCT[1] / 100 * prog)
    if wA > 8: d.rounded_rectangle((x0, y0, x0 + wA, y1), 30, fill=CYAN + (255,))
    if wB > 8: d.rounded_rectangle((x1 - wB, y0, x1, y1), 30, fill=PINK + (255,))
    tx(d, (540, 1250), "FINAL RESULT", SB(26), (255, 255, 255, int(160 * ease_out((tl - 1.0) / 0.4))), 'mm')
    logo(img); return img
def f_c3(tl):
    img = CCLIP.read(); rays(img, tl, 540, 760, GOLD, 36, n=18, speed=0.25, width=0.13); particles(img, tl, GOLD, 200)
    confetti(img, tl, 0.0)
    d = ImageDraw.Draw(img, 'RGBA')
    s = back((tl - 0.15) / 0.6); sz = max(8, int(560 * s))
    g = fade(glow(GOLD, 560, 140, 200), min(1, s)); img.paste(g, (540 - 280 - 140, 470 - 140), g)
    c = cover(CH, sz, 40); img.paste(c, (540 - sz // 2, 750 - sz // 2), c)
    d.rounded_rectangle((540 - sz // 2 - 8, 750 - sz // 2 - 8, 540 + sz // 2 + 8, 750 + sz // 2 + 8), 48, outline=GOLD + (255,), width=6)
    c_head(d, "CHAMPION")
    cs = back((tl - 0.5) / 0.5)
    if cs > 0.02: crown(d, 540, 454, 0.8 * min(cs, 1.0))
    ea = ease_out((tl - 0.9) / 0.4); n, a_ = TR[CH]; al = int(255 * ea)
    n2, fn_ = fitt(d, n, BEB, 118, 740, artist=True); a2, fa_ = fitt(d, a_, SB, 46, 740)
    tx(d, (540, 1105), n2, fn_, (255, 255, 255, al), 'mm'); tx(d, (540, 1180), a2, fa_, GOLD + (al,), 'mm')
    tx(d, (540, 1255), f"{PCT[0]}% OF THE VOTE", SB(38), (255, 255, 255, int(255 * ease_out((tl - 1.4) / 0.4))), 'mm')
    tx(d, (540, 1310), "THE ODOV AUDIENCE HAS SPOKEN", MD(26), (255, 255, 255, int(170 * ease_out((tl - 1.8) / 0.4))), 'mm')
    logo(img)
    fl = max(0, 1 - tl / 0.5)
    if fl > 0: img = Image.blend(img, Image.new('RGB', (W, H), (255, 255, 255)), fl)
    return img
def block(d, x0, x1, base, h, gold=False, a=1.0):
    top = base - int(h * a)
    if h * a < 4: return top
    d.rounded_rectangle((x0, top, x1, base), 16, fill=(255, 214, 64, 46) if gold else (255, 255, 255, 18), outline=GOLD + (255,) if gold else (255, 255, 255, 70), width=3)
    return top
def f_c4(tl):
    img = CCLIP.read(); rays(img, tl, 540, 700, GOLD, 24, speed=0.15); particles(img, tl); confetti(img, tl, -3.0, 0.45)
    d = ImageDraw.Draw(img, 'RGBA'); c_head(d, "TOP 4 OF 16")
    gt(img, (540, 520), "THE PODIUM", 120, ease_out(tl / 0.4))
    base = 1415
    for x0, x1, h, t0, idx, lab, gold in ((190, 410, 400, 0.3, RU, "2ND", False), (430, 650, 560, 0.9, CH, "1ST", True)):
        a = ease_out((tl - t0) / 0.5); top = block(d, x0, x1, base, h, gold, a)
        if a > 0.95:
            cx = (x0 + x1) // 2; ca = ease_out((tl - t0 - 0.45) / 0.35); cs = back((tl - t0 - 0.45) / 0.35)
            sz = max(4, int(200 * cs)); c = fade(cover(idx, sz, 28), ca); img.paste(c, (cx - sz // 2, top - 12 - sz), c)
            if gold: crown(d, cx, top - 12 - 200 - 10, 0.45 * cs)
            tx(d, (cx, top + 52), lab, BEB(64), GOLD if gold else (255, 255, 255), 'mm')
            n, a_ = TR[idx]; n2, fn_ = fitt(d, n, SB, 26, 196, 15, artist=True); a2, fa_ = fitt(d, a_, MD, 20, 196, 12)
            tx(d, (cx, top + 112), n2, fn_, (255, 255, 255, int(255 * ca)), 'mm'); tx(d, (cx, top + 148), a2, fa_, (190, 200, 215, int(255 * ca)), 'mm')
    a = ease_out((tl - 0.6) / 0.5); top = block(d, 670, 890, base, 300, False, a)
    if a > 0.95:
        ca = ease_out((tl - 1.05) / 0.35); cs = back((tl - 1.05) / 0.35)
        for j, idx in enumerate((S1, S2)):
            sz = max(4, int(100 * cs)); c = fade(cover(idx, sz, 16), ca); img.paste(c, (690 + j * 110 + (100 - sz) // 2, top - 12 - sz), c)
        tx(d, (780, top + 32), "SEMIFINALISTS", SB(18), (255, 255, 255, int(255 * ca)), 'mm')
        for j, idx in enumerate((S1, S2)):
            n2, fn_ = fitt(d, TR[idx][0], SB, 24, 196, 14, artist=True); a2, fa_ = fitt(d, TR[idx][1], MD, 17, 196, 11)
            tx(d, (780, top + 84 + j * 54), n2, fn_, (255, 255, 255, int(255 * ca)), 'mm'); tx(d, (780, top + 108 + j * 54), a2, fa_, (190, 200, 215, int(255 * ca)), 'mm')
    logo(img); return img
def f_c5(tl):
    img = BG.copy(); rays(img, tl, 540, 760, GOLD, 18, speed=0.1); particles(img, tl)
    d = ImageDraw.Draw(img, 'RGBA')
    e = ease_out(tl / 0.4); gt(img, (540, 470), "THANKS FOR VOTING", int(100 * (1 + 0.5 * (1 - e))), e)
    ea = ease_out((tl - 0.6) / 0.4)
    tx(d, (540, 650), "WANT MORE HARDSTYLE?", fit(d, "WANT MORE HARDSTYLE?", BEB, 92, 820), (255, 255, 255, int(255 * ea)), 'mm')
    eb = ease_out((tl - 1.0) / 0.4)
    tx(d, (540, 760), "THE WEEKLY HARDSTYLE CHART", SB(38), CYAN + (int(255 * eb),), 'mm')
    ec = ease_out((tl - 1.3) / 0.4)
    tx(d, (540, 820), "+  NEW RELEASES EVERY DAY", SB(38), CYAN + (int(255 * ec),), 'mm')
    es = back((tl - 1.6) / 0.5)
    if es > 0.02 and STICK is not None:
        sw = int(STICK.width * es); sh = int(STICK.height * es); st = STICK.resize((max(4, sw), max(4, sh)), Image.LANCZOS); img.paste(st, (540 - sw // 2, 1010 - sh // 2), st)
    tx(d, (540, 1190), "SEE YOU IN 2027", SB(30), (255, 255, 255, int(170 * ease_out((tl - 2.6) / 0.4))), 'mm')
    logo(img); return img
def frame_campio(fi):
    t = fi / FPS
    if t < T1: return f_c1(t)
    if t < T2: return f_c2(t - T1)
    if t < T3: return f_c3(t - T2)
    if t < T4: return f_c4(t - T3)
    return f_c5(t - T4)

# ============================ sortida ============================
def render_video(frame_fn, total, wav, out):
    n = int(total * FPS)
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
                          *VIDEO_OPTS, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-shortest', out], stdin=subprocess.PIPE)
    t0 = time.time()
    for fi in range(n):
        p.stdin.write(frame_fn(fi).convert('RGB').tobytes())
        if fi % 150 == 0: print(f"   fotograma {fi}/{n} ({time.time() - t0:.0f}s)", flush=True)
    p.stdin.close(); p.wait()
    if p.returncode != 0: raise SystemExit("ERROR: ffmpeg ha fallat")
def upload_release(tag, files, titol):
    if not GH_TOKEN or os.environ.get('TORNEIG_NO_UPLOAD'):
        print("(no es puja res al release: sense GITHUB_TOKEN o en mode prova)"); return
    h = {"Authorization": f"token {GH_TOKEN}"}
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}", headers=h)
    if r.status_code == 200:
        rel = r.json()
        for a in rel.get('assets', []):
            if a['name'] in [os.path.basename(f) for f in files]:
                requests.delete(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}", headers=h)
    else:
        r = requests.post(f"https://api.github.com/repos/{REPO}/releases", headers=h, json={"tag_name": tag, "name": titol, "draft": False})
        if r.status_code not in (200, 201): raise SystemExit(f"ERROR creant release: {r.status_code} {r.text}")
        rel = r.json()
    up = rel['upload_url'].split('{')[0]
    for f in files:
        ct = 'video/mp4' if f.endswith('.mp4') else 'image/png'
        with open(f, 'rb') as fh:
            r2 = requests.post(f"{up}?name={os.path.basename(f)}", headers={**h, "Content-Type": ct}, data=fh)
        print(f"Pujat {os.path.basename(f)}: {r2.status_code} ({os.path.getsize(f) / 1048576:.1f} MB)")

# ============================ main ============================
if __name__ == '__main__':
    print(f"Mode: {MODE}")
    if MODE == 'cuadre':
        done = len(RES)
        sub = "THE CHAMPION" if (3, 0) in RES else ("THE DRAW" if done == 0 else f"{done} / 15 PLAYED")
        img, _ = bracket_full(RES, None, sub, video=False); out = f"{OUTPUT}/cuadre.png"; img.save(out)
        upload_release("torneig_cuadre", [out], "torneig_cuadre")
    elif MODE == 'campio':
        if (3, 0) not in RES: raise SystemExit("ERROR: falta el resultat de la final")
        E = entrants(RES); CH = RES[(3, 0)][0]; RU = [x for x in E[3] if x != CH][0]; pc = RES[(3, 0)][1]
        if pc is None: raise SystemExit("ERROR: per al video del campio cal el percentatge de la final")
        PCT = (pc, 100 - pc)
        S1, S2 = [[x for x in (E[2][2 * mm], E[2][2 * mm + 1]) if x != RES[(2, mm)][0]][0] for mm in range(2)]
        T1, T2, T3, T4, TOTAL = 3.5, 7.5, 15.0, 21.0, 26.0
        CCLIP = Clip(CH, 14.0)
        mx = Mix(TOTAL); TH = thump(); HERO = [207.6, 415.3, 523.3, 622.3]
        mx.mono(riser(3.5), 0.0, 0.9)
        for tt in (1.5, 2.0, 2.45, 2.8, 3.1, 3.3): mx.mono(TH, tt, 0.5)
        for i in range(30):
            t = np.arange(int(SR * 0.03)) / SR; mx.mono(np.sin(2 * np.pi * (900 + i * 40) * t) * np.exp(-t * 120) * 0.25, T1 + 0.1 + i * 0.08)
        mx.mono(boom(3.0), T2, 1.0); mx.mono(chord(HERO, 6.0, g=0.18), T2)
        n = int(SR * 4.5); t = np.arange(n) / SR
        mx.mono(hpf(lpf(rng.standard_normal(n), 6500), 900) * (0.5 + 0.5 * np.abs(np.sin(t * 37))) * np.exp(-np.maximum(0, t - 2.5) * 1.0) * 0.35, T2 + 0.1, 0.7)
        au = CCLIP.audio.copy(); fo = int(1.5 * SR); au[-fo:] *= np.linspace(1, 0, fo)[:, None]
        mx.stereo(au, T2 + 0.3, 0.85)
        for tt in (T3 + 0.3, T3 + 0.6, T3 + 0.9): mx.mono(TH, tt, 0.6)
        mx.mono(whoosh(0.5, True), T3 - 0.1, 0.4); mx.mono(whoosh(0.5, False), T4 - 0.1, 0.4)
        mx.mono(chord([349.2, 440.0, 523.3, 698.5], 4.8, g=0.14), T4 + 0.05)
        wav = f"{OUTPUT}/aud.wav"; mx.save(wav)
        out = f"{OUTPUT}/video.mp4"; render_video(frame_campio, TOTAL, wav, out)
        img, _ = bracket_full(RES, None, "THE CHAMPION", video=False); cu = f"{OUTPUT}/cuadre.png"; img.save(cu)
        upload_release("torneig_campio", [out, cu], "torneig_campio")
    else:
        R, M = R_AVUI, M_AVUI; EPIC = (R == 3); pos = ORDRE.index((R, M))
        RES_VIEW = {k: v for k, v in RES.items() if ORDRE.index(k) < pos}
        E_VIEW = entrants(RES_VIEW); FA, FB = E_VIEW[R][2 * M], E_VIEW[R][2 * M + 1]
        if FA is None or FB is None: raise SystemExit("ERROR: encara no es coneixen els dos temes d'aquest partit (falten resultats anteriors)")
        PREV = RES.get(ORDRE[pos - 1]) if pos > 0 else None
        SUBTXT = f"{RONDES[R]}  ·  MATCH {M + 1} / {NM[R]}"
        INTRO, CLIP, BRK, VOTE = (6.0, 12.0, 5.0, 7.0) if EPIC else (3.0, 10.0, 4.5, 6.0)
        T_A = INTRO; T_B = T_A + CLIP; T_BR = T_B + CLIP; T_V = T_BR + BRK; TOTAL = T_V + VOTE
        print(f"{RONDES[R]} partit {M + 1}: {TR[FA][0]} vs {TR[FB][0]}  ({TOTAL:.1f} s)")
        BRK_IMG, META_BRK = bracket_full(RES_VIEW, (R, M), ("THE FINAL  ·  TODAY" if EPIC else f"{SUBTXT}  ·  TODAY"), video=True)
        CLIPS = [Clip(FA, CLIP + 1), Clip(FB, CLIP + 1)]
        mx = Mix(TOTAL); TH = thump(); HERO = [207.6, 415.3, 523.3, 622.3]
        if EPIC:
            mx.mono(riser(1.2), 0.0, 0.9); mx.mono(boom(2.5), 1.2, 1.0); mx.mono(chord(HERO, 4.8, g=0.16), 1.2)
            mx.mono(whoosh(0.7, True), 1.95, 0.4); mx.mono(whoosh(0.7, True), 2.1, 0.4); mx.mono(TH, 3.0, 1.0)
            for i in range(3): mx.mono(TH, 3.8 + 0.3 * i, 0.35)
            mx.mono(riser(0.6), T_V - 0.6, 0.5); mx.mono(boom(2.0), T_V, 0.9); mx.mono(chord(HERO, 5.5, g=0.14), T_V + 0.05)
            mx.mono(thump(), T_BR + 0.35, 0.8); mx.mono(chord([349.2, 415.3, 523.3], 4.5, g=0.10), T_BR + 0.3)
        else:
            mx.mono(whoosh(1.0, True), 0.0, 0.5); mx.mono(TH, 1.0, 1.0); mx.mono(whoosh(0.5, True), 0.45, 0.3)
            mx.mono(thump(), T_BR + 0.35, 0.7)
            for fq in (349.2, 415.3, 523.3):
                t = np.arange(int(SR * BRK)) / SR; mx.mono(lpf(2 * ((t * fq) % 1) - 1, 2200) * np.exp(-t * 0.7) * 0.10, T_BR + 0.3)
            mx.mono(TH, T_V + 0.35, 0.9); mx.mono(TH, T_V + 1.0, 0.8)
            for fq in (349.2, 415.3, 523.3):
                t = np.arange(int(SR * 5.0)) / SR; mx.mono(lpf(2 * ((t * fq) % 1) - 1, 2200) * np.exp(-t * 0.9) * 0.12, T_V + 0.35)
        mx.mono(whoosh(0.5, False), T_A - 0.1, 0.4); mx.mono(whoosh(0.5, True), T_B - 0.1, 0.4); mx.mono(whoosh(0.5, False), T_BR - 0.1, 0.4)
        for k, tt in enumerate((T_A, T_B)):
            au = CLIPS[k].audio[:int(CLIP * SR)].copy(); fo = int(0.25 * SR); au[-fo:] *= np.linspace(1, 0, fo)[:, None]; mx.stereo(au, tt, 1.0)
        wav = f"{OUTPUT}/aud.wav"; mx.save(wav)
        out = f"{OUTPUT}/video.mp4"; render_video(frame_versus, TOTAL, wav, out)
        img, _ = bracket_full(RES_VIEW, (R, M), ("THE FINAL  ·  TODAY" if EPIC else f"{SUBTXT}  ·  TODAY"), video=False); cu = f"{OUTPUT}/cuadre.png"; img.save(cu)
        upload_release(f"torneig_versus_{R}_{M}", [out, cu], f"torneig_versus_{R}_{M}")
    print("FET")
