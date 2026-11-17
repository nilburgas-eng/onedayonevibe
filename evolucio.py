# evolucio.py - format "EVOLUTION": un tema per any de la trajectoria d'un artista, amb linia de temps.
# Versio actualitzada: usa odov_comu.py (capcalera, portades robustes, zones segures de TikTok),
# qualitat maxima (fins a 4K, crf 12/16, AAC 320k/256k a 48 kHz) i volum uniforme entre clips.
import os, json, re, subprocess, base64, shutil, random
import librosa, numpy as np
from scipy.signal import find_peaks, butter, filtfilt
import requests

import odov_comu as OC

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

ARTISTA           = os.environ['ARTISTA']
ESTIL             = os.environ.get('ESTIL', 'energetic')
FONS_URL          = os.environ.get('FONS_URL', '').strip()    # video generic de fons (nomes visual; el so sempre es del tema)
MARGE_FONS        = 15.0     # no s'agafen imatges dels primers/ultims segons del video de fons
PADDING_FONS      = 1.0
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
COMPTE            = "@onedayonevibe"
SUBTITOL          = "Hard Dance"   # subtitol sota l'@ al final del video
DURADA_CLIP       = 8
DURADA_OUTRO      = 2.0            # el darrer clip dura DURADA_CLIP + DURADA_OUTRO (el "ara" de l'artista)
FADE_DURADA       = 0.3
DURADA_COMPTADOR  = 0.8            # l'any "puja" de l'any anterior a l'actual durant aquest temps
NORMALITZAR_VOLUM = True           # tots els clips al mateix volum (-14 LUFS), perque no hi hagi salts

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 16 -profile:v high -maxrate 24M -bufsize 48M -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -movflags +faststart"
VIDEO_OPTS_CLIP = "-c:v libx264 -preset fast -crf 12 -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709"
YTDLP_FORMAT = "bestvideo[height<=2160][vcodec!^=av01]+bestaudio[ext=m4a]/bestvideo[height<=2160][vcodec!^=av01]+bestaudio/bestvideo[height<=1440]+bestaudio/best[height<=1440]/best"

COLOR_ACCENT = "0x00BFFF"

LOGO_PATH    = "logo.png"
LOGO_W       = 90
LOGO_OPACITY = 0.85
LOGO_MARGIN  = 30
LOGO_ACTIU   = os.path.exists(LOGO_PATH)

COVER_W  = 280
COVER_H  = 280
COVER_X  = 90
COVER_Y  = 530
X_INFO   = 410          # text (any i nom) al costat de la portada
Y_ANY_VIS = 530         # el cim de l'any queda alineat amb el cim de la portada
Y_NOM_VIS = 660         # cim de la primera linia del nom
Y_BAR_MIN = 860         # linia de temps (mai per sobre d'aquest valor)
BAR_X    = 90
BAR_W    = 900          # acaba a x=990 (TikTok retalla els costats)
Y_OUTRO  = 1560
Y_OUTRO2 = 1618


def get_spotify_token():
    return OC.spotify_token(SPOTIFY_CLIENT_ID, SPOTIFY_SECRET)


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
        print(f"   ERROR consultant durada del video de fons: {e}")
        return None


def baixar_tros_fons(url, inici, durada_tros, output_path):
    fi = inici + durada_tros
    cmd = (
        f'yt-dlp -f "bestvideo[height<=2160][vcodec!^=av01]/bestvideo[height<=1440]/best[height<=1440]/best" '
        f'--download-sections "*{inici:.2f}-{fi:.2f}" --force-keyframes-at-cuts '
        f'--merge-output-format mp4 --cookies cookies.txt --js-runtime node '
        f'--remote-components ejs:github -o "{output_path}" "{url}" -q'
    )
    ret = os.system(cmd)
    return ret == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000


def partir_nom(nom, max_chars=22):
    if len(nom) <= max_chars:
        return nom, ""
    idx = nom.rfind(' ', 0, max_chars)
    if idx == -1:
        idx = max_chars
    return nom[:idx].strip(), nom[idx:].strip()


def trobar_moment_impactant(audio_path, duracio_total, estil='energetic'):
    try:
        audio, sr = librosa.load(audio_path, sr=22050, mono=True)
        hop_length = 512
        inici_cerca = min(30, duracio_total * 0.15)
        inici_sample = int(inici_cerca * sr)
        audio_tall = audio[inici_sample:]
        rms = librosa.feature.rms(y=audio_tall, frame_length=2048, hop_length=hop_length)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        rms_smooth = np.convolve(rms, np.ones(50)/50, mode='same')
        nyq = sr / 2
        if estil == 'melodic':
            b, a = butter(4, [500/nyq, 4000/nyq], btype='band')
            audio_target = filtfilt(b, a, audio_tall)
        elif estil == 'vocal':
            b_voc, a_voc = butter(4, [750/nyq, 2500/nyq], btype='band')
            audio_vocal = filtfilt(b_voc, a_voc, audio_tall)
            rms_vocal = librosa.feature.rms(y=audio_vocal, frame_length=2048, hop_length=hop_length)[0]
            rms_vocal_smooth = np.convolve(rms_vocal, np.ones(50)/50, mode='same')
            rms_combined = rms_vocal_smooth * 0.6 + rms_smooth * 0.4
            llindar = np.max(rms_smooth) * 0.65
            candidats, _ = find_peaks(rms_smooth, height=llindar, distance=sr//hop_length*15)
            if len(candidats) == 0:
                candidats = [np.argmax(rms_smooth)]
            millor = max(candidats, key=lambda i: rms_combined[min(i, len(rms_combined)-1)])
            moment = max(inici_cerca, inici_cerca + times[min(millor, len(times)-1)] - 2)
            return moment
        else:
            b, a = butter(4, 100/nyq, btype='low')
            audio_target = filtfilt(b, a, audio_tall)
        rms_target = librosa.feature.rms(y=audio_target, frame_length=2048, hop_length=hop_length)[0]
        rms_target_smooth = np.convolve(rms_target, np.ones(50)/50, mode='same')
        llindar = np.max(rms_smooth) * 0.65
        candidats, _ = find_peaks(rms_smooth, height=llindar, distance=sr//hop_length*15)
        if len(candidats) == 0:
            candidats = [np.argmax(rms_smooth)]
        millor = max(candidats, key=lambda i: rms_target_smooth[min(i, len(rms_target_smooth)-1)])
        moment = max(inici_cerca, inici_cerca + times[min(millor, len(times)-1)] - 2)
        return moment
    except Exception as e:
        print(f"   Error deteccio: {e}")
        return 30.0


def any_a_int(valor):
    s = str(valor if valor is not None else '').strip()
    return int(s) if s.isdigit() else None


def filtres_linia_temps(idx, n, anys, y_bar, accent):
    """Linia de temps amb un punt per any. El marcador gran viatja del tema anterior a l'actual (passos de 0.1 s)."""
    xs = [int(BAR_X + (BAR_W * k / (n - 1) if n > 1 else BAR_W / 2)) for k in range(n)]
    f = []
    f.append(f"drawbox=x={BAR_X}:y={y_bar}:w={BAR_W}:h=4:color=white@0.18:t=fill")
    # tram recorregut (omple fins al tema anterior; l'ultim tros s'anima)
    x_prev = xs[idx - 1] if idx > 0 else xs[0]
    x_cur = xs[idx]
    if idx > 0:
        f.append(f"drawbox=x={BAR_X}:y={y_bar}:w={max(x_prev - BAR_X, 1)}:h=4:color={accent}@0.9:t=fill")
    passos = 7
    pas = DURADA_COMPTADOR / passos
    if idx > 0:
        for s in range(1, passos + 1):
            p = 1 - (1 - s / passos) ** 3
            xm = int(x_prev + (x_cur - x_prev) * p)
            t0, t1 = (s - 1) * pas, s * pas
            f.append(f"drawbox=x={BAR_X}:y={y_bar}:w={max(xm - BAR_X, 1)}:h=4:color={accent}@0.9:t=fill:enable='between(t,{t0:.2f},{t1:.2f})'")
        f.append(f"drawbox=x={BAR_X}:y={y_bar}:w={max(x_cur - BAR_X, 1)}:h=4:color={accent}@0.9:t=fill:enable='gte(t,{DURADA_COMPTADOR:.2f})'")
    # punts petits (no el marcador)
    for k in range(n):
        if k == idx:
            continue
        col = f"{accent}@0.95" if k < idx else "white@0.35"
        f.append(f"drawbox=x={xs[k] - 7}:y={y_bar + 2 - 7}:w=14:h=14:color={col}:t=fill")
    # marcador gran
    if idx > 0:
        for s in range(1, passos + 1):
            p = 1 - (1 - s / passos) ** 3
            xm = int(x_prev + (x_cur - x_prev) * p)
            t0, t1 = (s - 1) * pas, s * pas
            en = f":enable='between(t,{t0:.2f},{t1:.2f})'"
            f.append(f"drawbox=x={xm - 15}:y={y_bar + 2 - 15}:w=30:h=30:color=white:t=fill{en}")
            f.append(f"drawbox=x={xm - 10}:y={y_bar + 2 - 10}:w=20:h=20:color={accent}:t=fill{en}")
        en = f":enable='gte(t,{DURADA_COMPTADOR:.2f})'"
    else:
        en = ""
    f.append(f"drawbox=x={x_cur - 15}:y={y_bar + 2 - 15}:w=30:h=30:color=white:t=fill{en}")
    f.append(f"drawbox=x={x_cur - 10}:y={y_bar + 2 - 10}:w=20:h=20:color={accent}:t=fill{en}")
    # anys sota els punts (si n'hi ha molts, nomes primer, actual i ultim)
    mostrar = set(range(n)) if n <= 12 else {0, idx, n - 1}
    for k in sorted(mostrar):
        if anys[k] is None:
            continue
        if k == idx:
            col, mida, fnt = accent, 28, FONT_EXTRABOLD
        elif k < idx:
            col, mida, fnt = "white@0.6", 24, FONT_SEMIBOLD
        else:
            col, mida, fnt = "white@0.3", 24, FONT_SEMIBOLD
        fil = OC.dt(str(anys[k]), fnt, mida, col, f"{xs[k]}-text_w/2", y_bar + 30, vora=2, ombra=1)
        f.append(fil)
    return f


print("Carregant tracks rebuts...")
TRACKS_RAW = os.environ.get('TRACKS', '')
tracks = json.loads(TRACKS_RAW)

for t in tracks:
    if t.get('timestamp_manual') not in (None, '', 0):
        t['timestamp_manual'] = float(t['timestamp_manual'])
    else:
        t['timestamp_manual'] = None

if not tracks:
    print("ERROR: No s'han rebut tracks")
    exit(1)

# l'evolucio va sempre d'abans a despres: ordenem per any (els que no en tenen, al final) i renumerem
tracks.sort(key=lambda t: (any_a_int(t.get('any')) is None, any_a_int(t.get('any')) or 0, t.get('pos', 0)))
for i, t in enumerate(tracks):
    t['pos'] = i + 1
ANYS = [any_a_int(t.get('any')) for t in tracks]


def durada_del_clip(t):
    return DURADA_CLIP + (DURADA_OUTRO if t['pos'] == len(tracks) else 0)


# video generic de fons: a cada tema marcat se li assigna un tros diferent (repartits per tot el video, amb una mica d'atzar)
offsets_fons = {}
if FONS_URL and any(t.get('visual_general') for t in tracks):
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
        for i, t in enumerate(tracks):
            dur = durada_del_clip(t)
            marge_bucket = max(0, bucket - dur)
            offset = usable_inici + i * bucket + random.uniform(0, marge_bucket)
            offsets_fons[t['pos']] = max(0, min(offset, durada_fons_total - dur - 0.5))
    else:
        print("   AVIS: no s'ha pogut consultar la durada, es descarta el video de fons")
        FONS_URL = ''

print(f"\nTracks ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t.get('any')} - {t['nom']}")

print("\nObtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify (les portades es busquen igualment a Deezer i iTunes)")

os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)
clips_paths = []

for idx, track in enumerate(tracks):
    pos              = track['pos']
    nom              = track['nom']
    any_canco        = any_a_int(track.get('any'))
    yt_url           = track.get('yt_url')
    timestamp_manual = track.get('timestamp_manual')
    nom_manual       = track.get('nom_manual')
    es_ultim         = (pos == len(tracks))
    durada           = DURADA_CLIP + (DURADA_OUTRO if es_ultim else 0)

    print(f"\nClip #{pos}: {any_canco} - {nom}")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/videos/{pos:02d}.wav")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")

    nom_cover = nom_manual if nom_manual else nom

    # ---- portada: Spotify -> Deezer -> iTunes (odov_comu); si no, miniatura de YouTube ----
    if not (os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000):
        try:
            cover_data, cover_font = OC.obtenir_portada(nom_cover, ARTISTA, spotify_token)
        except Exception as e:
            cover_data, cover_font = None, None
            print(f"   AVIS: error cercant portada ({e})")
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada OK ({cover_font})")
        else:
            print(f"   AVIS: sense portada a Spotify/Deezer/iTunes per '{nom_cover}'")

    nom_query = nom.replace("'", "").replace('"', '').strip()
    if any(x in nom.lower() for x in ['remix', 'edit', 'mix', 'version']):
        query = f"{ARTISTA} {nom_query} official"
    else:
        query = f"{ARTISTA} {nom_query} {ARTISTA} official video"

    if not (os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000):
        os.system(f'yt-dlp --write-thumbnail --skip-download --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{thumb_path.replace(".jpg","")}" "ytsearch1:{query}" -q 2>/dev/null')
        thumb_webp = thumb_path.replace(".jpg", ".webp")
        if not os.path.exists(thumb_path) and os.path.exists(thumb_webp):
            os.system(f'ffmpeg -i "{thumb_webp}" "{thumb_path}" -y -loglevel error')

    # ---- video ----
    if yt_url:
        font = yt_url
        print(f"   URL manual: {yt_url}")
    else:
        font = f"ytsearch1:{query}"
    if os.path.exists(video_path) and os.path.getsize(video_path) > 10000:
        ret = 0
    else:
        ret = os.system(f'yt-dlp -f "{YTDLP_FORMAT}" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font}" --no-playlist -q')

    sense_video = (ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000)
    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    if sense_video:
        # no hi ha videoclip: fons amb la portada difuminada i silenci, pero el clip porta igualment l'any i la linia de temps
        print(f"   AVIS: no s'ha trobat videoclip per '{nom}' - clip sense video (portada difuminada, sense so)")
        if has_thumb:
            os.system(f'ffmpeg -loop 1 -i "{thumb_path}" -f lavfi -i anullsrc=r=48000:cl=stereo -t {durada + 1} -vf "scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=40:5,fps=30" {VIDEO_OPTS_CLIP} -c:a aac -b:a 320k -ar 48000 -shortest "{video_path}" -y -loglevel error')
        else:
            os.system(f'ffmpeg -f lavfi -i color=c=black:s=1080x1920:d={durada + 1} -f lavfi -i anullsrc=r=48000:cl=stereo -t {durada + 1} -r 30 {VIDEO_OPTS_CLIP} -c:a aac -b:a 320k -ar 48000 -shortest "{video_path}" -y -loglevel error')
        if not os.path.exists(video_path):
            print("   ERROR: no s'ha pogut crear el clip de reserva")
            continue
        duracio_total = durada + 1
        inici = 0.0
    else:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path], capture_output=True, text=True)
        info = json.loads(r.stdout)
        duracio_total = float(info['format']['duration'])
        for s in info.get('streams', []):
            if s.get('codec_type') == 'video':
                print(f"   Resolucio baixada: {s.get('width')}x{s.get('height')}")
                break

        os.system(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{audio_path}" -y -loglevel error')

        if timestamp_manual is not None:
            inici = float(timestamp_manual)
            print(f"   Timestamp manual: {int(inici//60):02d}:{int(inici%60):02d}")
        else:
            inici = trobar_moment_impactant(audio_path, duracio_total, ESTIL) if os.path.exists(audio_path) else 30.0
        # que el clip no es passi del final del video
        inici = max(0.0, min(inici, max(0.0, duracio_total - durada - 0.5)))

    # ---- imatge del video generic de fons (si s'ha marcat per aquest tema); el so continua sent del tema ----
    usar_fons_visual = False
    fons_path = os.path.expanduser(f"~/fons_{pos:02d}.mp4")
    if track.get('visual_general') and FONS_URL and pos in offsets_fons:
        offset_fons = offsets_fons[pos]
        print(f"   Imatge del video generic seleccionada ({int(offset_fons//60):02d}:{int(offset_fons%60):02d})")
        ok_fons = baixar_tros_fons(FONS_URL, max(0, offset_fons - PADDING_FONS), durada + 2 * PADDING_FONS, fons_path)
        if ok_fons:
            usar_fons_visual = True
        else:
            print("   AVIS: no s'ha pogut baixar el tram generic, s'usa la imatge propia")
    elif track.get('visual_general') and not FONS_URL:
        print("   AVIS: has marcat imatge generica pero no hi ha video de fons; s'usa la imatge propia")

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
    nom_mostrat = OC.neteja(nom_manual if nom_manual else nom)

    # ---- textos ----
    _amb_portada = has_thumb
    _x_info = X_INFO if _amb_portada else BAR_X
    txt = []
    txt += OC.degradat_dalt(560, 0.55) + OC.degradat_baix(1480, 0.5)
    _t_lin, _t_mida = OC.titol_en_linies(ARTISTA.upper(), FONT_BEBAS)
    _items = [dict(text=l, font=FONT_BEBAS, mida=_t_mida, color='white', gap=(0 if i == 0 else 8)) for i, l in enumerate(_t_lin)]
    _items.append(dict(text="EVOLUTION", font=FONT_SEMIBOLD, mida=40, color=COLOR_ACCENT, gap=16, filets=True, vora=2, ombra=2))
    _hdr, _ = OC.capcalera(_items)
    txt += _hdr

    # any gran (puja de l'any anterior a l'actual)
    if any_canco is not None:
        _dalt_any, _ = OC._alcada_visible(FONT_EXTRABOLD, 120)
        y_any = Y_ANY_VIS - _dalt_any
        if idx > 0 and ANYS[idx - 1] is not None and ANYS[idx - 1] != any_canco:
            ant = ANYS[idx - 1]
            expr = f"if(lt(t,{DURADA_COMPTADOR}),{ant}+({any_canco}-{ant})*t/{DURADA_COMPTADOR},{any_canco})"
            text_any = "%{eif\\:" + expr + "\\:d}"
        else:
            text_any = str(any_canco)
        txt.append(OC.dt(text_any, FONT_EXTRABOLD, 120, 'white', _x_info, y_any, vora=3, ombra=3))
        y_nom0 = Y_NOM_VIS
    else:
        y_nom0 = Y_ANY_VIS

    # nom del tema (fins a 2 linies, amb "..." si no hi cap)
    _dalt_nom, _ = OC._alcada_visible(FONT_SEMIBOLD, 56)
    _linies = OC.parteix_linies(nom_mostrat, FONT_SEMIBOLD, 56, OC.X_SEGUR_DRETA - _x_info, max_linies=2)
    y_vis = y_nom0
    for l in _linies:
        txt.append(OC.dt(l, FONT_SEMIBOLD, 56, 'white', _x_info, y_vis - _dalt_nom, vora=3, ombra=2))
        y_vis += 66
    _y_bar = max(Y_BAR_MIN, int(max(y_vis, COVER_Y + COVER_H)) + 50)
    txt += filtres_linia_temps(idx, len(tracks), ANYS, _y_bar, COLOR_ACCENT)

    if es_ultim:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=50:fontcolor=white@0.82:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_OUTRO}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='{SUBTITOL}':fontsize=30:fontcolor={COLOR_ACCENT}@0.70:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y={Y_OUTRO2}:enable='gte(t,{t_aparicio})'")

    txt_str = ",".join(txt)

    # ---- muntatge del clip ----
    input_parts = [f'-ss {inici} -i "{video_path}"']
    seguent = 1
    visual_idx = 0
    if usar_fons_visual:
        offset_dins_tros = min(PADDING_FONS, offsets_fons[pos])
        input_parts.append(f'-ss {offset_dins_tros:.2f} -i "{fons_path}"')
        visual_idx = seguent
        seguent += 1
    thumb_idx = logo_idx = None
    if has_thumb:
        input_parts.append(f'-i "{thumb_path}"')
        thumb_idx = seguent
        seguent += 1
    if LOGO_ACTIU:
        input_parts.append(f'-i "{LOGO_PATH}"')
        logo_idx = seguent
        seguent += 1
    inputs = " ".join(input_parts)

    fc_parts = [f"[{visual_idx}:v]scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,unsharp=5:5:0.4:5:5:0.0[bg]"]
    if has_thumb:
        fc_parts.append(
            f"[{thumb_idx}:v]scale={COVER_W}:{COVER_H}:flags=lanczos:force_original_aspect_ratio=decrease,"
            f"pad={COVER_W}:{COVER_H}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[cover]"
        )
        fc_parts.append(f"[bg][cover]overlay={COVER_X}:{COVER_Y}[withcover]")
        fc_parts.append("[withcover]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    else:
        fc_parts.append("[bg]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    fc_parts.append(f"[colored]{txt_str}[out]")
    if NORMALITZAR_VOLUM and not sense_video:
        fc_parts.append("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        fc_parts.append("[0:a]aresample=48000[aout]")
    if LOGO_ACTIU:
        fc_parts.append(f"[{logo_idx}:v]scale={LOGO_W}:-1:flags=lanczos,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[logo]")
        fc_parts.append(f"[out][logo]overlay=W-w-{LOGO_MARGIN}:{LOGO_MARGIN}[final]")
        mapa_final = "[final]"
    else:
        mapa_final = "[out]"

    fc = ";".join(fc_parts)
    cmd = f'ffmpeg {inputs} -t {durada} -filter_complex "{fc}" -map "{mapa_final}" -map "[aout]" {VIDEO_OPTS_CLIP} -r 30 -c:a aac -b:a 320k -ar 48000 "{output_path}" -y -loglevel error'
    os.system(cmd)
    clips_paths.append((pos, output_path))
    print(f"   OK clip generat")

clips_paths.sort(key=lambda x: x[0])
clips_valids = []
for pos, path in clips_paths:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        clips_valids.append(path)
    else:
        print(f"   Clip #{pos} descartat: {path}")

if len(clips_valids) < 2:
    print("ERROR: No hi ha prou clips valids")
    exit(1)

print(f"\nMuntant video final amb {len(clips_valids)} clips...")
durades = []
for path in clips_valids:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    durades.append(float(json.loads(r.stdout)['format']['duration']))

n_clips = len(clips_valids)
inputs_str = " ".join([f"-i '{p}'" for p in clips_valids])
video_filters = []
audio_filters = []
prev_v, prev_a = "0:v", "0:a"
offset = 0.0
for i in range(1, n_clips):
    offset += durades[i-1] - FADE_DURADA
    ultim = (i == n_clips - 1)
    out_v = "vfinal" if ultim else f"v{i}"
    out_a = "afinal" if ultim else f"a{i}"
    video_filters.append(f"[{prev_v}][{i}:v]xfade=transition=fade:duration={FADE_DURADA}:offset={offset:.3f}[{out_v}]")
    audio_filters.append(f"[{prev_a}][{i}:a]acrossfade=d={FADE_DURADA}[{out_a}]")
    prev_v, prev_a = out_v, out_a

filter_complex = ";".join(video_filters + audio_filters)
output_final = f"{OUTPUT}/evolucio_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 256k -ar 48000 "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
