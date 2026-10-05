import os, json, re, subprocess, base64, shutil, random
import requests
try:
    from PIL import ImageFont
    PIL_OK = True
except Exception:
    PIL_OK = False

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

SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
FONS_URL          = os.environ.get('FONS_URL', '').strip()    # video generic de fons (nomes visual, com top10drops)
MARGE_FONS        = 15.0
PADDING_FONS      = 1.0
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
TITOL_X           = os.environ.get('TITOL_X', '').strip()
COMPTE            = "@onedayonevibe"
GUESS_DURADA      = 3.3
TRANSICIO_DURADA  = 0.4
REVEAL_DURADA     = 1.3
DURADA_RONDA      = GUESS_DURADA + TRANSICIO_DURADA + REVEAL_DURADA   # 5.0s
# Desenfocament (gaussia): sigma inicial i passos fins a nitid. Es va 'enfocant' en 4 passos durant la transicio.
BLUR_INICIAL        = 26
BLUR_PASSOS_REVEAL  = [15, 8, 3]
# El nom/artista es desenfoca menys que la portada: si no, s'esborraria del tot i perdria l'efecte d'alguna cosa amagada
BLUR_TEXT_INICIAL       = 12
BLUR_TEXT_PASSOS_REVEAL = [7, 4, 2]
RECAP_DURADA      = 1.0
FADE_DURADA       = 0.3

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"

SPEED_FACTOR = 1.03

COLOR_ACCENT = "0x00BFFF"
COLOR_WHITE  = "white"

COVER_W  = 420
COVER_H  = 420
COVER_X  = (1080 - COVER_W) // 2
COVER_Y  = 460

Y_TITOL1    = 190
BAR_X       = COVER_X
BAR_Y       = COVER_Y + COVER_H + 40
BAR_W       = COVER_W
BAR_SEGMENTS = 60   # la barra de compte enrere es dibuixa com a 60 segments que van desapareixent
BANDA_TOP_H       = 430    # banda fosca sota el titol i l'etiqueta N/8
BANDA_RESULTAT_H  = 280    # banda fosca sota la barra, amb nom i artista
BANDA_OPACITAT    = 0.35
Y_RESULTAT1 = BAR_Y + 60
Y_RESULTAT2 = Y_RESULTAT1 + 65

LOGO_PATH    = "logo.png"
LOGO_W       = 90
LOGO_OPACITY = 0.85
LOGO_MARGIN  = 30
LOGO_ACTIU   = os.path.exists(LOGO_PATH)

def trobar_fitxer_sense_distingir_majuscules(nom_base):
    for f in os.listdir('.'):
        if f.lower() == nom_base.lower():
            return f
    return None

STICKER_FOLLOW_PATH = trobar_fitxer_sense_distingir_majuscules("sticker_follow.png") or "sticker_follow.png"
STICKER_THANKS_PATH = trobar_fitxer_sense_distingir_majuscules("sticker_thanks.png") or "sticker_thanks.png"
STICKER_ACTIU = os.path.exists(STICKER_FOLLOW_PATH) and os.path.exists(STICKER_THANKS_PATH)
STICKER_W = 220
STICKER_Y = 1450

# ---------- PROVA: logo fix a baix + boto FOLLOW a la meitat del video (igual que chart2) ----------
# True  = el logo surt sempre a baix, just sobre del @compte del final. A la meitat del video apareix el
#         boto FOLLOW (gran) just a sobre del logo, i despres el Thanks.
# False = comportament anterior (logo a la cantonada + Follow/Thanks al principi).
PROVA_FOLLOW_MIG = True
LOGO_CENTRE_W    = 120    # amplada del logo
LOGO_CENTRE_CY   = 1488   # centre vertical del logo: a baix, just sobre del @compte del final (y=1560)
FOLLOW_W         = 437    # amplada total del sticker (el boto visible en fa ~77%)
FOLLOW_GAP       = 14     # separacio entre el boto i el logo
THANKS_MIG       = True   # despres del Follow, mostrar el Thanks
FOLLOW_DURADA    = 2.1
THANKS_DURADA    = 1.8
CTA_FADE         = 0.3
LOGO_PER_CLIP    = LOGO_ACTIU and not PROVA_FOLLOW_MIG
STICKER_PER_CLIP = STICKER_ACTIU and not PROVA_FOLLOW_MIG
# valors per defecte (stickers de 1215x1295) per si no es pot llegir la imatge
DEF_FOLLOW = (0.47413, 0.78764, 1295 / 1215)
DEF_THANKS = (0.49807, 0.70039, 1295 / 1215)

def mesurar_cta(path, per_defecte):
    """Prepara un sticker per quedar-nos nomes amb el boto, sense l'emblema de dalt.
    Torna (y0, y1, aspect): primera fila despres de l'emblema, ultima fila visible (fraccions de l'alcada)
    i alcada/amplada de la imatge. Si no es pot llegir (p. ex. sense Pillow), torna 'per_defecte'."""
    try:
        from PIL import Image
        alfa = Image.open(path).convert('RGBA').getchannel('A')
        w, h = alfa.size
        dades = alfa.tobytes()
        files = [dades[y * w:(y + 1) * w] for y in range(h)]
        visibles = [y for y in range(h) if max(files[y]) > 20]
        c0, c1 = int(w * 0.40), int(w * 0.60)          # franja central, per on baixa l'emblema
        y0 = None
        for y in range(visibles[0], h):
            if max(files[y][c0:c1]) <= 20:              # primera fila amb el centre buit: l'emblema ja ha acabat
                y0 = y
                break
        if y0 is None or y0 >= visibles[-1]:
            y0 = int(visibles[0] + 0.45 * (visibles[-1] - visibles[0]))
        return y0 / h, (visibles[-1] + 1) / h, h / w
    except Exception as e:
        print(f"   AVIS: no s'ha pogut mesurar el sticker ({e}), uso mides per defecte")
        return per_defecte



def trobar_fitxer_per_prefix(prefix):
    """Busca un fitxer al directori actual que comenci per 'prefix', sigui quina sigui l'extensio."""
    for f in os.listdir('.'):
        if f.lower().startswith(prefix.lower()):
            return f
    return None


def get_spotify_token():
    try:
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET}".encode()).decode()
        r = requests.post("https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"})
        return r.json().get('access_token')
    except:
        return None

def get_spotify_cover(nom_canco, artista, token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        query = f"track:{nom_canco} artist:{artista}"
        r = requests.get(f"https://api.spotify.com/v1/search?q={requests.utils.quote(query)}&type=track&limit=1", headers=headers)
        items = r.json().get('tracks', {}).get('items', [])
        if items:
            return requests.get(items[0]['album']['images'][0]['url']).content
    except:
        pass
    return None

def get_spotify_artist_image(artista, token):
    if not artista:
        return None
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"https://api.spotify.com/v1/search?q={requests.utils.quote(artista)}&type=artist&limit=1", headers=headers)
        items = r.json().get('artists', {}).get('items', [])
        if items and items[0].get('images'):
            return requests.get(items[0]['images'][0]['url']).content
    except:
        pass
    return None

def get_durada_video_remot(url):
    try:
        r = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-download', '--cookies', 'cookies.txt',
             '--js-runtime', 'node', '--remote-components', 'ejs:github', url],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0 or not r.stdout:
            return None
        info = json.loads(r.stdout.splitlines()[0])
        durada = info.get('duration')
        return float(durada) if durada else None
    except Exception as e:
        print(f"   ERROR consultant durada del link general: {e}")
        return None

def baixar_tros_fons(url, inici, durada_tros, output_path):
    fi = inici + durada_tros
    cmd = (
        f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]/best[ext=mp4]/best" '
        f'--download-sections "*{inici:.2f}-{fi:.2f}" --force-keyframes-at-cuts '
        f'--merge-output-format mp4 --cookies cookies.txt --js-runtime node '
        f'--remote-components ejs:github -o "{output_path}" "{url}" -q'
    )
    ret = os.system(cmd)
    return ret == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000

def get_youtube_thumbnail(yt_url):
    if not yt_url:
        return None
    m = re.search(r'(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})', yt_url)
    if not m:
        return None
    vid = m.group(1)
    for qualitat in ['maxresdefault', 'hqdefault']:
        try:
            r = requests.get(f"https://img.youtube.com/vi/{vid}/{qualitat}.jpg", timeout=15)
            if r.status_code == 200 and len(r.content) > 2000:
                return r.content
        except:
            pass
    return None


def mida_que_hi_cap(text, font_path, mida_max, mida_min, ample_max, factor_estimat=0.55):
    """Mida de font mes gran (entre mida_max i mida_min) perque el text càpiga en ample_max px.
    Mesura amb la tipografia real si Pillow hi es; si no, fa una estimacio."""
    for mida in range(mida_max, mida_min - 1, -2):
        ample = None
        if PIL_OK:
            try:
                ample = ImageFont.truetype(font_path, mida).getlength(text)
            except Exception:
                ample = None
        if ample is None:
            ample = len(text) * mida * factor_estimat
        if ample <= ample_max:
            return mida
    return mida_min


TRACKS_RAW = os.environ.get('TRACKS', '')
print("Carregant tracks rebuts...")
tracks = json.loads(TRACKS_RAW)
for t in tracks:
    if t.get('timestamp_manual') not in (None, '', 0):
        t['timestamp_manual'] = float(t['timestamp_manual'])
    else:
        t['timestamp_manual'] = None

if len(tracks) < 2:
    print("ERROR: calen com a minim 2 rondes")
    exit(1)

print(f"\nRondes ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")

print("\nObtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify")

max_pos = max(t['pos'] for t in tracks)

# Numeracio segons l'ordre real de reproduccio: el primer que sona es 1/N (les posicions mes altes sonen primer)
N_TOTAL = len(tracks)
numero_ronda = {t['pos']: i + 1 for i, t in enumerate(sorted(tracks, key=lambda t: t['pos'], reverse=True))}
if PROVA_FOLLOW_MIG:
    print("\nPROVA ACTIVA: logo a baix + Follow/Thanks a la meitat del video")
elif STICKER_ACTIU:
    print(f"\nStickers Follow/Thanks actius, apareixeran a la primera ronda (#{max_pos})")

offsets_fons = {}
if FONS_URL:
    print(f"\nVideo generic de fons (nomes visual): {FONS_URL}")
    durada_fons_total = get_durada_video_remot(FONS_URL)
    if durada_fons_total:
        print(f"   Durada total: {int(durada_fons_total//60):02d}:{int(durada_fons_total%60):02d}")
        n = len(tracks)
        usable_inici = MARGE_FONS
        usable_fi = max(MARGE_FONS, durada_fons_total - MARGE_FONS)
        usable = max(0, usable_fi - usable_inici)
        if usable <= 0:
            usable_inici = 0
            usable = durada_fons_total
        bucket = usable / n
        for i, track in enumerate(sorted(tracks, key=lambda t: t['pos'])):
            durada_ronda_i = DURADA_RONDA
            marge_bucket = max(0, bucket - durada_ronda_i)
            inici_bucket = usable_inici + i * bucket
            offset = inici_bucket + random.uniform(0, marge_bucket)
            offsets_fons[track['pos']] = max(0, min(offset, durada_fons_total - durada_ronda_i - 0.5))
    else:
        print(f"   AVIS: no s'ha pogut consultar la durada, es descarta el video de fons")
        FONS_URL = ''

clips_paths = []

for track in tracks:
    pos              = track['pos']
    nom              = track['nom']
    artista          = track.get('artista', '')
    yt_url           = track.get('yt_url')
    timestamp_manual = track.get('timestamp_manual')
    ronda_num        = numero_ronda[pos]

    es_ultim  = (pos == 1)
    es_primer = (pos == max_pos)
    durada = DURADA_RONDA
    reveal_t = GUESS_DURADA
    dificultat = (track.get('dificultat') or 'EASY').upper()

    print(f"\nRonda {ronda_num} (#{pos}): {nom} - {artista} [{dificultat}]")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    # ---------- PORTADA (ordre fix: Spotify tema -> artista -> YouTube propi) ----------
    if spotify_token:
        cover_data = get_spotify_cover(nom, artista, spotify_token)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada Spotify OK")
    if (not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000) and spotify_token:
        cover_data = get_spotify_artist_image(artista, spotify_token)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada Spotify artista OK (fallback)")
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        cover_data = get_youtube_thumbnail(yt_url)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada YouTube OK (fallback)")
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        print(f"   AVIS: cap portada trobada per aquest track")

    # ---------- CANCO ----------
    if yt_url:
        print(f"   URL manual: {yt_url}")
        ret = os.system(f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{yt_url}" --no-playlist -q')
    else:
        font_cerca = f"ytsearch1:{artista} {nom} official audio"
        print(f"   Cerca: {artista} {nom}")
        ret = os.system(f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font_cerca}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   ERROR: no s'ha pogut baixar l'audio - ronda descartada")
        continue

    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path], capture_output=True, text=True)
    info = json.loads(r.stdout)
    duracio_total = float(info['format']['duration'])

    if timestamp_manual is not None:
        inici = float(timestamp_manual)
        print(f"   Timestamp manual (el drop): {int(inici//60):02d}:{int(inici%60):02d}")
    else:
        inici = 30.0
        print(f"   AVIS: sense timestamp manual, usant 00:30 per defecte")
    inici = max(0, min(inici, duracio_total - durada - 0.5))

    usar_fons_visual = False
    fons_path = os.path.expanduser(f"~/videos/{pos:02d}_fons.mp4")
    if FONS_URL and pos in offsets_fons:
        offset_fons = offsets_fons[pos]
        inici_baixada = max(0, offset_fons - PADDING_FONS)
        durada_baixada = durada + 2 * PADDING_FONS
        print(f"   Video generic pel fons visual ({int(offset_fons//60):02d}:{int(offset_fons%60):02d})")
        ok_fons = baixar_tros_fons(FONS_URL, inici_baixada, durada_baixada, fons_path)
        if ok_fons:
            usar_fons_visual = True
        else:
            print(f"   AVIS: no s'ha pogut baixar el tram generic, s'usa el video propi")

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-').strip().rstrip(' -\u2013\u2014')
    artista_net = artista.replace("'", "").replace('"', '').replace(':', '-').strip().rstrip(' -\u2013\u2014')

    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    titol_complet = f"GUESS THE {TITOL_X.upper()} DROP" if TITOL_X else "GUESS THE DROP"
    etiqueta_ronda = f"{ronda_num}/{N_TOTAL} \u00b7 {dificultat}"

    txt = []
    txt.append(f"drawbox=x=0:y=0:w=1080:h={BANDA_TOP_H}:color=black@{BANDA_OPACITAT}:t=fill")
    txt.append(f"drawbox=x=0:y={BAR_Y - 30}:w=1080:h={BANDA_RESULTAT_H}:color=black@{BANDA_OPACITAT}:t=fill")
    mida_titol = mida_que_hi_cap(titol_complet, FONT_BEBAS, 108, 56, 940, factor_estimat=0.42)
    y_ronda = Y_TITOL1 + mida_titol + 30
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol_complet}':fontsize={mida_titol}:fontcolor=white:borderw=3:bordercolor=black@0.7:shadowx=0:shadowy=3:x=(w-text_w)/2:y={Y_TITOL1}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{etiqueta_ronda}':fontsize=44:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={y_ronda}")

    txt.append(f"drawbox=x={BAR_X}:y={BAR_Y}:w={BAR_W}:h=5:color=white@0.15:t=fill")
    seg_w = BAR_W / BAR_SEGMENTS
    for k in range(BAR_SEGMENTS):
        x_k = int(round(BAR_X + k * seg_w))
        x_seg_seguent = int(round(BAR_X + (k + 1) * seg_w))
        w_k = max(1, x_seg_seguent - x_k)
        t_lim = GUESS_DURADA * (1 - k / BAR_SEGMENTS)
        txt.append(f"drawbox=x={x_k}:y={BAR_Y}:w={w_k}:h=5:color={COLOR_ACCENT}:t=fill:enable='lt(t,{t_lim:.3f})'")

    resultat1 = f"{nom_net}"
    resultat2 = f"{artista_net}"
    # El nom i l'artista es dibuixen en una capa propia (mes avall) perque es puguin desenfocar igual que la portada.

    txt_str = ",".join(txt)

    input_parts = [f'-ss {inici} -i "{video_path}"']
    audio_idx = 0
    visual_idx = 0
    seguent_idx = 1

    if usar_fons_visual:
        offset_dins_tros = min(PADDING_FONS, offsets_fons[pos])
        input_parts.append(f'-ss {offset_dins_tros:.2f} -i "{fons_path}"')
        visual_idx = seguent_idx
        seguent_idx += 1

    thumb_idx = None
    if has_thumb:
        input_parts.append(f'-loop 1 -framerate 30 -i "{thumb_path}"')
        thumb_idx = seguent_idx
        seguent_idx += 1

    logo_idx = None
    if LOGO_PER_CLIP:
        input_parts.append(f'-i "{LOGO_PATH}"')
        logo_idx = seguent_idx
        seguent_idx += 1

    sticker_follow_idx = None
    sticker_thanks_idx = None
    if es_primer and STICKER_PER_CLIP:
        input_parts.append(f'-loop 1 -i "{STICKER_FOLLOW_PATH}"')
        sticker_follow_idx = seguent_idx
        seguent_idx += 1
        input_parts.append(f'-loop 1 -i "{STICKER_THANKS_PATH}"')
        sticker_thanks_idx = seguent_idx
        seguent_idx += 1

    inputs = " ".join(input_parts)

    fc_parts = [f"[{visual_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2[bg]"]

    current = "bg"
    if has_thumb:
        n_nivells = 2 + len(BLUR_PASSOS_REVEAL)   # blur inicial + passos + nitid
        raws = [f"cvraw{j}" for j in range(n_nivells)]
        fc_parts.append(
            f"[{thumb_idx}:v]scale={COVER_W}:{COVER_H}:force_original_aspect_ratio=decrease,"
            f"pad={COVER_W}:{COVER_H}:(ow-iw)/2:(oh-ih)/2:color=black@0.9,setsar=1,"
            f"split={n_nivells}" + "".join(f"[{r}]" for r in raws)
        )
        sigmes = [BLUR_INICIAL] + BLUR_PASSOS_REVEAL
        for j, sg in enumerate(sigmes):
            fc_parts.append(f"[{raws[j]}]gblur=sigma={sg}:steps=3[cvl{j}]")
        fc_parts.append(f"[{raws[-1]}]copy[cvsharp]")

        pas_dur = TRANSICIO_DURADA / len(BLUR_PASSOS_REVEAL)
        fc_parts.append(f"[{current}][cvl0]overlay={COVER_X}:{COVER_Y}:enable='lt(t,{reveal_t})'[cvo0]")
        anterior = "cvo0"
        for j in range(len(BLUR_PASSOS_REVEAL)):
            t0 = reveal_t + j * pas_dur
            t1 = t0 + pas_dur
            fc_parts.append(
                f"[{anterior}][cvl{j+1}]overlay={COVER_X}:{COVER_Y}:enable='gte(t,{t0:.3f})*lt(t,{t1:.3f})'[cvo{j+1}]"
            )
            anterior = f"cvo{j+1}"
        t_nitid = reveal_t + TRANSICIO_DURADA
        fc_parts.append(f"[{anterior}][cvsharp]overlay={COVER_X}:{COVER_Y}:enable='gte(t,{t_nitid:.3f})'[withcover]")
        current = "withcover"

    fc_parts.append(f"[{current}]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    fc_parts.append(f"[colored]{txt_str}[txbase]")

    # ---- Capa del nom + artista: desenfocada igual que la portada i es revela amb ella ----
    mida_nom = mida_que_hi_cap(resultat1, FONT_EXTRABOLD, 56, 30, 980, factor_estimat=0.62)
    mida_art = mida_que_hi_cap(resultat2, FONT_SEMIBOLD, 44, 26, 980, factor_estimat=0.60)
    y_nom_capa = 12
    y_art_capa = y_nom_capa + mida_nom + 14
    capa_h = y_art_capa + mida_art + 22
    y_capa = Y_RESULTAT1 - y_nom_capa
    n_nivells_t = 2 + len(BLUR_TEXT_PASSOS_REVEAL)
    raws_t = [f"txraw{j}" for j in range(n_nivells_t)]
    fc_parts.append(
        f"color=c=black@0.0:s=1080x{capa_h}:r=30:d={durada + 1},format=rgba,"
        f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{resultat1}':fontsize={mida_nom}:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x=(w-text_w)/2:y={y_nom_capa},"
        f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{resultat2}':fontsize={mida_art}:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.8:x=(w-text_w)/2:y={y_art_capa},"
        f"split={n_nivells_t}" + "".join(f"[{r}]" for r in raws_t)
    )
    sigmes_t = [BLUR_TEXT_INICIAL] + BLUR_TEXT_PASSOS_REVEAL
    for j, sg in enumerate(sigmes_t):
        fc_parts.append(f"[{raws_t[j]}]gblur=sigma={sg}:steps=3[tl{j}]")
    fc_parts.append(f"[{raws_t[-1]}]copy[tlsharp]")

    pas_dur_t = TRANSICIO_DURADA / len(BLUR_TEXT_PASSOS_REVEAL)
    fc_parts.append(f"[txbase][tl0]overlay=0:{y_capa}:enable='lt(t,{reveal_t})'[tlo0]")
    anterior_t = "tlo0"
    for j in range(len(BLUR_TEXT_PASSOS_REVEAL)):
        t0 = reveal_t + j * pas_dur_t
        t1 = t0 + pas_dur_t
        fc_parts.append(f"[{anterior_t}][tl{j+1}]overlay=0:{y_capa}:enable='gte(t,{t0:.3f})*lt(t,{t1:.3f})'[tlo{j+1}]")
        anterior_t = f"tlo{j+1}"
    fc_parts.append(f"[{anterior_t}][tlsharp]overlay=0:{y_capa}:enable='gte(t,{reveal_t + TRANSICIO_DURADA:.3f})'[txlay]")
    fc_parts.append(f"[txlay]setpts=PTS/{SPEED_FACTOR}[txted]")

    fc_parts.append(f"[{audio_idx}:a]atempo={SPEED_FACTOR}[aout]")

    if es_primer and STICKER_PER_CLIP:
        fc_parts.append(
            f"[{sticker_follow_idx}:v]scale={STICKER_W}:-1,format=rgba,"
            f"fade=t=in:st=0.3:d=0.3:alpha=1,fade=t=out:st=1.4:d=0.3:alpha=1[stfollow]"
        )
        fc_parts.append(
            f"[{sticker_thanks_idx}:v]scale={STICKER_W}:-1,format=rgba,"
            f"fade=t=in:st=1.4:d=0.3:alpha=1,fade=t=out:st=2.5:d=0.3:alpha=1[stthanks]"
        )
        fc_parts.append(f"[txted][stfollow]overlay=(W-w)/2:{STICKER_Y}:enable='between(t,0.3,1.7)'[stk1]")
        fc_parts.append(f"[stk1][stthanks]overlay=(W-w)/2:{STICKER_Y}:enable='between(t,1.4,2.8)'[out]")
    else:
        fc_parts.append("[txted]copy[out]")

    if LOGO_PER_CLIP:
        fc_parts.append(f"[{logo_idx}:v]scale={LOGO_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[logo]")
        fc_parts.append(f"[out][logo]overlay=W-w-{LOGO_MARGIN}:{LOGO_MARGIN}[final]")
        mapa_final = "[final]"
    else:
        mapa_final = "[out]"

    fc = ";".join(fc_parts)
    cmd = f'ffmpeg {inputs} -t {durada} -filter_complex "{fc}" -map "{mapa_final}" -map "[aout]" {VIDEO_OPTS} -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    mida = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    if mida > 1000:
        print(f"   OK ronda generada ({mida//1024} KB)")
    else:
        print(f"   ERROR: ronda #{pos} no generada correctament (mida={mida})")
        print(f"   FFMPEG STDERR: {result.stderr[-1500:]}")
    clips_paths.append((pos, output_path))

# ---------- PANTALLA FINAL: "HOW MANY DID YOU GET?" ----------
recap_path = f"{OUTPUT}/clip_99_recap.mp4"
txt_recap = []
txt_recap.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='HOW MANY DID YOU GET?':fontsize=52:fontcolor=white:borderw=2:bordercolor=black@0.7:x=(w-text_w)/2:y=780")
txt_recap.append(f"drawtext=fontfile='{FONT_BEBAS}':text='__/{N_TOTAL}':fontsize=140:fontcolor={COLOR_ACCENT}:borderw=3:bordercolor=black@0.8:x=(w-text_w)/2:y=880")
txt_recap.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='COMMENT YOUR SCORE':fontsize=40:fontcolor=white@0.85:borderw=2:bordercolor=black@0.7:x=(w-text_w)/2:y=1080")
compte_text = COMPTE.replace("'", "")
txt_recap.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=40:fontcolor=white@0.85:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y=1550")
txt_recap.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='One Day One Vibe':fontsize=28:fontcolor={COLOR_ACCENT}@0.75:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y=1608")
txt_recap_str = ",".join(txt_recap)

input_parts_recap = [f'-f lavfi -i color=c=0x0d0d0d:s=1080x1920:d={RECAP_DURADA}', '-f lavfi -i anullsrc=r=44100:cl=stereo']
seguent_idx_recap = 2
logo_idx_recap = None
if LOGO_PER_CLIP:
    input_parts_recap.append(f'-i "{LOGO_PATH}"')
    logo_idx_recap = seguent_idx_recap
    seguent_idx_recap += 1
inputs_recap = " ".join(input_parts_recap)

fc_recap = [f"[0:v]{txt_recap_str}[txted]"]
if LOGO_PER_CLIP:
    fc_recap.append(f"[{logo_idx_recap}:v]scale={LOGO_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[logo]")
    fc_recap.append(f"[txted][logo]overlay=W-w-{LOGO_MARGIN}:{LOGO_MARGIN}[out]")
    mapa_recap = "[out]"
else:
    mapa_recap = "[txted]"
fc_recap_str = ";".join(fc_recap)

cmd_recap = f'ffmpeg {inputs_recap} -t {RECAP_DURADA} -filter_complex "{fc_recap_str}" -map "{mapa_recap}" -map 1:a {VIDEO_OPTS} -r 30 -c:a aac -b:a 192k -ar 44100 -shortest "{recap_path}" -y -loglevel error'
result_recap = subprocess.run(cmd_recap, shell=True, capture_output=True, text=True)
mida_recap = os.path.getsize(recap_path) if os.path.exists(recap_path) else 0
if mida_recap > 1000:
    print(f"\nPantalla final generada ({mida_recap//1024} KB)")
else:
    print(f"\nERROR: pantalla final no generada correctament")
    print(f"   FFMPEG STDERR: {result_recap.stderr[-1500:]}")
    recap_path = None

clips_paths.sort(key=lambda x: x[0], reverse=True)
clips_valids = []
for pos, path in clips_paths:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        clips_valids.append(path)
    else:
        print(f"   Ronda #{pos} descartada: {path}")

if recap_path and os.path.exists(recap_path) and os.path.getsize(recap_path) > 1000:
    clips_valids.append(recap_path)

if len(clips_valids) < 2:
    print("ERROR: No hi ha prou rondes valides")
    exit(1)

print(f"\nMuntant video final amb {len(clips_valids)} rondes...")
durades = []
for path in clips_valids:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    durades.append(float(json.loads(r.stdout)['format']['duration']))

n_clips = len(clips_valids)
inputs_str = " ".join([f"-i '{p}'" for p in clips_valids])
video_filters = []
audio_filters = []
offset = durades[0] - FADE_DURADA

if n_clips == 2:
    video_filters.append(f"[0:v][1:v]xfade=transition=fade:duration={FADE_DURADA}:offset={offset}[vfinal]")
    audio_filters.append(f"[0:a][1:a]acrossfade=d={FADE_DURADA}[afinal]")
else:
    video_filters.append(f"[0:v][1:v]xfade=transition=fade:duration={FADE_DURADA}:offset={offset}[v01]")
    audio_filters.append(f"[0:a][1:a]acrossfade=d={FADE_DURADA}[a01]")
    for i in range(2, n_clips):
        prev_v = f"v0{i-1}"
        prev_a = f"a0{i-1}"
        out_v = f"v0{i}" if i < n_clips - 1 else "vfinal"
        out_a = f"a0{i}" if i < n_clips - 1 else "afinal"
        offset += durades[i-1] - FADE_DURADA
        video_filters.append(f"[{prev_v}][{i}:v]xfade=transition=fade:duration={FADE_DURADA}:offset={offset:.3f}[{out_v}]")
        audio_filters.append(f"[{prev_a}][{i}:a]acrossfade=d={FADE_DURADA}[{out_a}]")

overlay_filters = []
extra_inputs = ""
limit_durada = ""
mapa_video = "[vfinal]"
durada_final = sum(durades) - FADE_DURADA * (n_clips - 1)

if PROVA_FOLLOW_MIG and (LOGO_ACTIU or STICKER_ACTIU):
    idx = n_clips
    t0 = durada_final / 2                      # el Follow surt just a la meitat del video
    actual = "[vfinal]"

    # --- logo fix a baix, sempre visible ---
    logo_top = LOGO_CENTRE_CY - 49             # valor per defecte si no es pot llegir el logo
    if LOGO_ACTIU:
        try:
            from PIL import Image
            lw, lh = Image.open(LOGO_PATH).size
            logo_top = LOGO_CENTRE_CY - (LOGO_CENTRE_W * lh / lw) / 2
        except Exception:
            pass
        extra_inputs += f' -loop 1 -framerate 30 -i "{LOGO_PATH}"'
        logo_i = idx
        idx += 1
        overlay_filters.append(
            f"[{logo_i}:v]scale={LOGO_CENTRE_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[lgone]")
        overlay_filters.append(f"{actual}[lgone]overlay=(W-w)/2:{LOGO_CENTRE_CY}-h/2[vl2]")
        actual = "[vl2]"

    # --- boto FOLLOW (i despres THANKS) just a sobre del logo, sense l'emblema del sticker ---
    if STICKER_ACTIU:
        y0f, y1f, asp_f = mesurar_cta(STICKER_FOLLOW_PATH, DEF_FOLLOW)
        y0t, y1t, asp_t = mesurar_cta(STICKER_THANKS_PATH, DEF_THANKS)
        alt_boto = (y1f - y0f) * FOLLOW_W * asp_f              # alcada visible del boto Follow, en pixels
        sy = round(logo_top - FOLLOW_GAP - alt_boto)           # el Thanks va a la mateixa alcada
        print(f"   Follow mig: boto de {FOLLOW_W}px just sobre el logo (y={sy}), apareix a {t0:.1f}s de {durada_final:.1f}s")
        extra_inputs += f' -loop 1 -framerate 30 -i "{STICKER_FOLLOW_PATH}"'
        follow_i = idx
        idx += 1
        overlay_filters.append(
            f"[{follow_i}:v]scale={FOLLOW_W}:-1,format=rgba,crop=iw:ih*{y1f - y0f:.5f}:0:ih*{y0f:.5f},"
            f"fade=t=in:st={t0:.3f}:d={CTA_FADE}:alpha=1,"
            f"fade=t=out:st={t0 + FOLLOW_DURADA - CTA_FADE:.3f}:d={CTA_FADE}:alpha=1[stf]")
        etiqueta = "[vl3]" if THANKS_MIG else "[vout]"
        overlay_filters.append(
            f"{actual}[stf]overlay=(W-w)/2:{sy}:enable='between(t,{t0:.3f},{t0 + FOLLOW_DURADA:.3f})'{etiqueta}")
        actual = etiqueta
        if THANKS_MIG:
            t_th = t0 + FOLLOW_DURADA - CTA_FADE
            extra_inputs += f' -loop 1 -framerate 30 -i "{STICKER_THANKS_PATH}"'
            thanks_i = idx
            idx += 1
            overlay_filters.append(
                f"[{thanks_i}:v]scale={FOLLOW_W}:-1,format=rgba,crop=iw:ih*{y1t - y0t:.5f}:0:ih*{y0t:.5f},"
                f"fade=t=in:st={t_th:.3f}:d={CTA_FADE}:alpha=1,"
                f"fade=t=out:st={t_th + THANKS_DURADA - CTA_FADE:.3f}:d={CTA_FADE}:alpha=1[stt]")
            overlay_filters.append(
                f"{actual}[stt]overlay=(W-w)/2:{sy}:enable='between(t,{t_th:.3f},{t_th + THANKS_DURADA:.3f})'[vout]")
            actual = "[vout]"
    else:
        overlay_filters.append(f"{actual}copy[vout]")
        actual = "[vout]"
    mapa_video = "[vout]"
    limit_durada = f"-t {durada_final + 0.05:.3f}"

filter_complex = ";".join(video_filters + overlay_filters + audio_filters)
output_final = f"{OUTPUT}/guessthetrack_final.mp4"
cmd = f'ffmpeg {inputs_str}{extra_inputs} -filter_complex "{filter_complex}" -map "{mapa_video}" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 192k {limit_durada} "{output_final}" -y -loglevel error'
ret_final = os.system(cmd)
if ret_final != 0 or not os.path.exists(output_final) or os.path.getsize(output_final) < 10000:
    print(f"ERROR: muntatge final ha fallat (codi {ret_final})")
else:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", output_final], capture_output=True, text=True)
    durada_total = float(json.loads(r.stdout)['format']['duration'])
    print(f"Video final generat! Durada: {durada_total:.1f}s amb {n_clips} rondes")
