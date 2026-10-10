import os, re, subprocess, json, sys

# ============================================================
#  HOOK - video lliure: tram de YouTube + marca ODOV
#  (el hook de text/veu l'afegeixes tu a TikTok)
#
#  Entrades (variables d'entorn):
#    URL    enllac de YouTube
#    INICI  inici del tram  (mm:ss, h:mm:ss o segons)
#    FI     final del tram  (mm:ss, h:mm:ss o segons)
#    MODE   omplir (defecte, omple els 9:16 retallant)  |  difuminat (video sencer + fons difuminat)
#    FOLLOW si (defecte) | no
# ============================================================

OUTPUT = os.path.expanduser("~/output")
FONTS  = os.path.expanduser("~/fonts")
os.makedirs(OUTPUT, exist_ok=True)

FONT_SEMIBOLD = f"{FONTS}/Montserrat-SemiBold.ttf"
FONT_MEDIUM   = f"{FONTS}/Montserrat-Medium.ttf"
FONT_FALLBACK = f"{FONTS}/Montserrat-Bold.ttf"
if not os.path.exists(FONT_SEMIBOLD) or os.path.getsize(FONT_SEMIBOLD) < 1000:
    FONT_SEMIBOLD = FONT_FALLBACK
if not os.path.exists(FONT_MEDIUM) or os.path.getsize(FONT_MEDIUM) < 1000:
    FONT_MEDIUM = FONT_FALLBACK

COMPTE       = "@onedayonevibe"
TAGLINE      = "One Day One Vibe"
COLOR_ACCENT = "0x00BFFF"

SPEED_FACTOR  = 1.03     # mateixa acceleracio subtil que la resta de formats (1.0 = desactivat)
PADDING       = 2.0      # segons extra que es baixen abans/despres del tram per tallar be
DURADA_OUTRO  = 2.0
OUTRO_FADE    = 0.3

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"

# --- logo fix a baix + Follow just a sobre a la meitat (igual que la resta de formats) ---
LOGO_CENTRE_W  = 120
LOGO_CENTRE_CY = 1488
LOGO_OPACITY   = 0.85
FOLLOW_W       = 437
FOLLOW_GAP     = 14
FOLLOW_DURADA  = 2.1
THANKS_DURADA  = 1.8
CTA_FADE       = 0.3
FOLLOW_MIN_CLIP = 12.0   # si el clip dura menys, no es posa el Follow

# --- nom del tema (a dalt) i artista (a sota), en petit, opcionals ---
INFO_T_INICI   = 2.5     # segons: apareix despres del hook, per retenir
INFO_FADE      = 0.4
INFO_Y_TEMA    = 960     # una mica per sota del mig, deixant l'espai de dalt lliure pel hook de TikTok
INFO_Y_ARTISTA = 1020
INFO_MIDA_TEMA    = 44
INFO_MIDA_ARTISTA = 32
INFO_AMPLE_MAX    = 840  # evita els botons de la dreta de TikTok
DEF_FOLLOW = (0.47413, 0.78764, 1295 / 1215)
DEF_THANKS = (0.49807, 0.70039, 1295 / 1215)


def trobar_fitxer(prefix, extensions=(".png",)):
    """Busca un fitxer a l'arrel sense distingir majuscules. Accepta 'sticker_follow.png', 'Sticker_Follow.PNG'
    i tambe la doble extensio 'sticker_follow.png.PNG'."""
    prefix = prefix.lower()
    candidats = []
    for f in os.listdir('.'):
        fl = f.lower()
        if not fl.startswith(prefix):
            continue
        if any(fl.endswith(e) for e in extensions):
            candidats.append(f)
    if not candidats:
        return None
    candidats.sort(key=lambda n: (len(n), n))      # el nom mes curt (el mes "net") primer
    return candidats[0]


LOGO_PATH = trobar_fitxer("logo") or "logo.png"
LOGO_ACTIU = os.path.exists(LOGO_PATH)
STICKER_FOLLOW_PATH = trobar_fitxer("sticker_follow") or "sticker_follow.png"
STICKER_THANKS_PATH = trobar_fitxer("sticker_thanks") or "sticker_thanks.png"
STICKER_ACTIU = os.path.exists(STICKER_FOLLOW_PATH) and os.path.exists(STICKER_THANKS_PATH)


def mesurar_cta(path, per_defecte):
    """Mesura on acaba l'emblema del sticker per quedar-nos nomes amb el boto.
    Torna (y0, y1, aspect) en fraccions de l'alcada."""
    try:
        from PIL import Image
        alfa = Image.open(path).convert('RGBA').getchannel('A')
        w, h = alfa.size
        dades = alfa.tobytes()
        files = [dades[y * w:(y + 1) * w] for y in range(h)]
        visibles = [y for y in range(h) if max(files[y]) > 20]
        c0, c1 = int(w * 0.40), int(w * 0.60)
        y0 = None
        for y in range(visibles[0], h):
            if max(files[y][c0:c1]) <= 20:
                y0 = y
                break
        if y0 is None or y0 >= visibles[-1]:
            y0 = int(visibles[0] + 0.45 * (visibles[-1] - visibles[0]))
        return y0 / h, (visibles[-1] + 1) / h, h / w
    except Exception as e:
        print(f"   AVIS: no s'ha pogut mesurar el sticker ({e}), uso mides per defecte")
        return per_defecte


def mida_que_hi_cap(text, font_path, mida_max, ample_max, mida_min=20):
    """Redueix la mida de la lletra fins que el text cap a l'amplada indicada."""
    try:
        from PIL import ImageFont
        mida = mida_max
        while mida > mida_min:
            bb = ImageFont.truetype(font_path, mida).getbbox(text)
            if bb[2] - bb[0] <= ample_max:
                break
            mida -= 1
        return mida
    except Exception:
        # sense Pillow: estimacio grollera (~0.6 de la mida per caracter)
        return max(mida_min, min(mida_max, int(ample_max / (0.6 * max(1, len(text))))))


def escriure_text(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def parse_temps(valor, nom):
    s = str(valor).strip().replace(',', '.')
    if not s:
        print(f"ERROR: falta {nom}")
        sys.exit(1)
    try:
        if ':' in s:
            total = 0.0
            for part in s.split(':'):
                total = total * 60 + float(part)
            return total
        return float(s)
    except ValueError:
        print(f"ERROR: {nom} no es un temps valid: '{valor}' (usa mm:ss, per exemple 1:23)")
        sys.exit(1)


def durada_fitxer(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        dur = float(d['format']['duration'])
        te_audio = any(s.get('codec_type') == 'audio' for s in d.get('streams', []))
        return dur, te_audio
    except Exception:
        return 0.0, False


FORMATS = [
    "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best",
    "best",
]


def baixar_tram(url, inici, fi, path):
    """Baixa nomes el tram [inici, fi] del video, sense baixar-lo sencer."""
    for fmt in FORMATS:
        if os.path.exists(path):
            os.remove(path)
        cmd = ["yt-dlp", "-4", "-f", fmt,
               "--download-sections", f"*{inici:.2f}-{fi:.2f}", "--force-keyframes-at-cuts",
               "--merge-output-format", "mp4",
               "--cookies", "cookies.txt", "--js-runtime", "node", "--remote-components", "ejs:github",
               "--no-playlist", "-o", path, url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 10000:
            return True
        print(f"   YT-DLP STDERR: {r.stderr[-1500:]}")
        print(f"   YT-DLP STDOUT: {r.stdout[-500:]}")
        print("   Provo amb un altre format...")
    return False


# ---------------- entrada ----------------
URL    = os.environ.get('URL', '').strip()
MODE   = os.environ.get('MODE', 'omplir').strip().lower()
FOLLOW = os.environ.get('FOLLOW', 'si').strip().lower() not in ('no', 'false', '0')
TEMA   = os.environ.get('TEMA', '').strip()
ARTISTA = os.environ.get('ARTISTA', '').strip()

if not URL:
    print("ERROR: falta l'enllac de YouTube (URL)")
    sys.exit(1)

INICI = parse_temps(os.environ.get('INICI', ''), 'INICI')
FI    = parse_temps(os.environ.get('FI', ''), 'FI')
if FI <= INICI:
    print(f"ERROR: el final ({FI:.1f}s) ha de ser posterior a l'inici ({INICI:.1f}s)")
    sys.exit(1)
if FI - INICI > 180:
    print(f"ERROR: el tram dura {FI - INICI:.0f}s; el maxim son 180s (3 minuts)")
    sys.exit(1)

print(f"URL: {URL}")
print(f"Tram: {INICI:.2f}s -> {FI:.2f}s ({FI - INICI:.2f}s) | mode: {MODE} | follow: {FOLLOW}")

# ---------------- descarrega ----------------
os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)
brut = os.path.expanduser("~/videos/hook_brut.mp4")

dl_start = max(0.0, INICI - PADDING)
dl_end   = FI + PADDING
seek_in  = INICI - dl_start

print("\nBaixant el tram...")
if not baixar_tram(URL, dl_start, dl_end, brut):
    print("ERROR: no s'ha pogut baixar el tram de YouTube")
    sys.exit(1)

dur_real, te_audio = durada_fitxer(brut)
print(f"   Tram baixat: {dur_real:.2f}s, audio: {'si' if te_audio else 'no'}")
if dur_real <= seek_in + 0.5:
    print("ERROR: el tram baixat es massa curt (comprova que el final no passa de la durada del video)")
    sys.exit(1)

clip_dur = min(FI - INICI, dur_real - seek_in)
if clip_dur < FI - INICI - 0.2:
    print(f"   AVIS: el video acaba abans del previst; el clip dura {clip_dur:.1f}s")
out_dur = clip_dur / SPEED_FACTOR
print(f"   Durada final del video: {out_dur:.2f}s")

# ---------------- filtres ----------------
filtres = []
if MODE.startswith('dif'):
    filtres.append(f"[0:v]fps=30,setpts=PTS/{SPEED_FACTOR},split=2[va][vb]")
    filtres.append("[va]scale=216:384:force_original_aspect_ratio=increase,crop=216:384,gblur=sigma=3,"
                   "scale=1080:1920:flags=bicubic,setsar=1,eq=brightness=-0.10[bg]")
    filtres.append("[vb]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg]")
    filtres.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[base]")
else:
    filtres.append(f"[0:v]fps=30,setpts=PTS/{SPEED_FACTOR},scale=1080:1920:force_original_aspect_ratio=increase,"
                   "crop=1080:1920,setsar=1[base]")

# franja fosca molt suau a baix perque el logo i el compte es llegeixin sobre qualsevol imatge
filtres.append("[base]drawbox=x=0:y=1580:w=1080:h=340:color=black@0.18:t=fill[vb0]")
actual = "[vb0]"

extra_inputs = ""
idx = 1    # l'input 0 es el video

# logo fix a baix
logo_top = LOGO_CENTRE_CY - 49
if LOGO_ACTIU:
    try:
        from PIL import Image
        lw, lh = Image.open(LOGO_PATH).size
        logo_top = LOGO_CENTRE_CY - (LOGO_CENTRE_W * lh / lw) / 2
    except Exception:
        pass
    extra_inputs += f' -loop 1 -framerate 30 -i "{LOGO_PATH}"'
    filtres.append(f"[{idx}:v]scale={LOGO_CENTRE_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[lg]")
    filtres.append(f"{actual}[lg]overlay=(W-w)/2:{LOGO_CENTRE_CY}-h/2[vl]")
    actual = "[vl]"
    idx += 1
else:
    print("AVIS: no trobo logo.png, el video sortira sense logo")

# Follow (i Thanks) a la meitat, just sobre el logo
t0 = out_dur / 2
follow_actiu = FOLLOW and STICKER_ACTIU and out_dur >= FOLLOW_MIN_CLIP
if FOLLOW and not STICKER_ACTIU:
    print("AVIS: no trobo sticker_follow.png / sticker_thanks.png, el video sortira sense Follow")
elif FOLLOW and out_dur < FOLLOW_MIN_CLIP:
    print(f"   Clip de {out_dur:.1f}s (< {FOLLOW_MIN_CLIP:.0f}s): no poso el Follow")

if follow_actiu:
    y0f, y1f, asp_f = mesurar_cta(STICKER_FOLLOW_PATH, DEF_FOLLOW)
    y0t, y1t, asp_t = mesurar_cta(STICKER_THANKS_PATH, DEF_THANKS)
    alt_boto = (y1f - y0f) * FOLLOW_W * asp_f
    sy = round(logo_top - FOLLOW_GAP - alt_boto)
    print(f"   Follow: y={sy}, apareix a {t0:.1f}s de {out_dur:.1f}s")

    extra_inputs += f' -loop 1 -framerate 30 -i "{STICKER_FOLLOW_PATH}"'
    fi_ = idx; idx += 1
    filtres.append(
        f"[{fi_}:v]scale={FOLLOW_W}:-1,format=rgba,crop=iw:ih*{y1f - y0f:.5f}:0:ih*{y0f:.5f},"
        f"fade=t=in:st={t0:.3f}:d={CTA_FADE}:alpha=1,"
        f"fade=t=out:st={t0 + FOLLOW_DURADA - CTA_FADE:.3f}:d={CTA_FADE}:alpha=1[stf]")
    filtres.append(f"{actual}[stf]overlay=(W-w)/2:{sy}:enable='between(t,{t0:.3f},{t0 + FOLLOW_DURADA:.3f})'[vf]")
    actual = "[vf]"

    t_th = t0 + FOLLOW_DURADA - CTA_FADE
    extra_inputs += f' -loop 1 -framerate 30 -i "{STICKER_THANKS_PATH}"'
    ti_ = idx; idx += 1
    filtres.append(
        f"[{ti_}:v]scale={FOLLOW_W}:-1,format=rgba,crop=iw:ih*{y1t - y0t:.5f}:0:ih*{y0t:.5f},"
        f"fade=t=in:st={t_th:.3f}:d={CTA_FADE}:alpha=1,"
        f"fade=t=out:st={t_th + THANKS_DURADA - CTA_FADE:.3f}:d={CTA_FADE}:alpha=1[stt]")
    filtres.append(f"{actual}[stt]overlay=(W-w)/2:{sy}:enable='between(t,{t_th:.3f},{t_th + THANKS_DURADA:.3f})'[vt]")
    actual = "[vt]"

# nom del tema (dalt) + artista (sota), en petit, amb fade a partir dels 2-3 s
if TEMA or ARTISTA:
    t_info = min(INFO_T_INICI, out_dur * 0.4)
    alfa_info = f"if(lt(t,{t_info:.3f}),0,min(1,(t-{t_info:.3f})/{INFO_FADE}))"
    linies_info = []
    y_actual = INFO_Y_TEMA
    if TEMA:
        mida = mida_que_hi_cap(TEMA, FONT_SEMIBOLD, INFO_MIDA_TEMA, INFO_AMPLE_MAX)
        f_tema = escriure_text(os.path.expanduser("~/videos/info_tema.txt"), TEMA)
        linies_info.append(
            f"drawtext=fontfile='{FONT_SEMIBOLD}':textfile='{f_tema}':expansion=none:fontsize={mida}:fontcolor=white@0.95:"
            f"borderw=2:bordercolor=black@0.7:x=(w-text_w)/2:y={y_actual}:alpha='{alfa_info}':enable='gte(t,{t_info:.3f})'")
        y_actual = INFO_Y_ARTISTA
    if ARTISTA:
        mida = mida_que_hi_cap(ARTISTA, FONT_MEDIUM, INFO_MIDA_ARTISTA, INFO_AMPLE_MAX)
        f_art = escriure_text(os.path.expanduser("~/videos/info_artista.txt"), ARTISTA)
        linies_info.append(
            f"drawtext=fontfile='{FONT_MEDIUM}':textfile='{f_art}':expansion=none:fontsize={mida}:fontcolor={COLOR_ACCENT}@0.95:"
            f"borderw=2:bordercolor=black@0.7:x=(w-text_w)/2:y={y_actual}:alpha='{alfa_info}':enable='gte(t,{t_info:.3f})'")
    filtres.append(f"{actual}" + ",".join(linies_info) + "[vinfo]")
    actual = "[vinfo]"
    print(f"   Info del tema: '{TEMA}' / '{ARTISTA}' (apareix a {t_info:.1f}s)")

# outro: @compte + tagline els darrers segons
dur_outro = min(DURADA_OUTRO, out_dur / 2)
t_out = out_dur - dur_outro
alfa = f"if(lt(t,{t_out:.3f}),0,min(1,(t-{t_out:.3f})/{OUTRO_FADE}))"
filtres.append(
    f"{actual}"
    f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{COMPTE}':fontsize=50:fontcolor=white@0.82:"
    f"borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y=1560:alpha='{alfa}':enable='gte(t,{t_out:.3f})',"
    f"drawtext=fontfile='{FONT_MEDIUM}':text='{TAGLINE}':fontsize=30:fontcolor={COLOR_ACCENT}@0.70:"
    f"borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y=1618:alpha='{alfa}':enable='gte(t,{t_out:.3f})'[vout]")

# audio
if te_audio:
    fade_out = min(0.4, out_dur / 4)
    filtres.append(f"[0:a]atempo={SPEED_FACTOR},afade=t=in:st=0:d=0.12,"
                   f"afade=t=out:st={out_dur - fade_out:.3f}:d={fade_out:.3f}[afinal]")
    mapa_audio = '-map "[afinal]" -c:a aac -b:a 192k'
else:
    mapa_audio = '-an'

filter_complex = ";".join(filtres)
output_final = f"{OUTPUT}/hook_final.mp4"
if os.path.exists(output_final):
    os.remove(output_final)

cmd = (f'ffmpeg -ss {seek_in:.3f} -t {clip_dur:.3f} -i "{brut}"{extra_inputs} '
       f'-filter_complex "{filter_complex}" -map "[vout]" {mapa_audio} '
       f'{VIDEO_OPTS} -r 30 -t {out_dur:.3f} -movflags +faststart "{output_final}" -y -loglevel error')
print("\nMuntant el video final...")
ret = os.system(cmd)
if ret != 0 or not os.path.exists(output_final) or os.path.getsize(output_final) < 10000:
    print(f"ERROR: muntatge final ha fallat (codi {ret})")
    sys.exit(1)

dur_fin, _ = durada_fitxer(output_final)
print(f"\nVideo final OK: {os.path.getsize(output_final) / 1024 / 1024:.1f} MB, {dur_fin:.1f}s")
