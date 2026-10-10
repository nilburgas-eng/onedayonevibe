import os, json, re, subprocess, base64, shutil, random
import librosa, numpy as np
from scipy.signal import find_peaks, butter, filtfilt
import requests

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

ESTIL             = os.environ.get('ESTIL', 'energetic')
FANOF             = os.environ.get('FANOF', 'HARDSTYLE')
PART              = os.environ.get('PART', '1')
COVER_FONT        = os.environ.get('COVER_FONT', 'spotify')   # 'spotify' o 'youtube'
FONS_URL          = os.environ.get('FONS_URL', '').strip()    # video generic de fons (opcional, nomes visual, com top10drops)
MARGE_FONS        = 15.0   # segons a evitar al principi/final del video de fons
PADDING_FONS      = 1.0    # marge extra de seguretat al baixar cada tros
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
COMPTE            = "@onedayonevibe"
DURADA_CLIP       = 8
DURADA_TOP1       = 12
DURADA_OUTRO      = 2.0
FADE_DURADA       = 0.3

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"
YTDLP_FORMAT = 'bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best'

SPEED_FACTOR = 1.03   # acceleracio subtil audio+video. 1.0 = desactivat

COLOR_ACCENT = "0x00BFFF"

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
STICKER_Y = 1180

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


NIVELLS = {
    'SUPER EASY': "0x1DB954",
    'EASY':       "0xA3E635",
    'MEDIUM':     "0xFFD700",
    'HARD':       "0xFF8C00",
    'VERY HARD':  "0xFF6B00",
    'EXPERT':     "0xFF4444",
    'LEGEND':     "0xFFD700",
}
NIVELL_DEFAULT = {7: 'SUPER EASY', 6: 'EASY', 5: 'MEDIUM', 4: 'HARD', 3: 'VERY HARD', 2: 'EXPERT', 1: 'LEGEND'}
NIVELL_DEFAULT = {5: 'VERY EASY', 4: 'EASY', 3: 'MEDIUM', 2: 'HARD', 1: 'EXTREME'}

COVER_W  = 280
COVER_H  = 280
COVER_X  = 90
COVER_Y  = 620
X_INFO   = 410
Y_NUM    = 620
Y_NOM1   = 760
Y_NOM2   = 830
Y_TITOL1 = 260
Y_TITOL1B = 325
Y_TITOL2 = 402
Y_NIVELL = 910
Y_ARTISTA = 980
Y_BAR    = 1060
BAR_X    = 90
BAR_W    = 980
Y_OUTRO  = 1560
Y_OUTRO2 = 1618

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

def get_durada_video_remot(url):
    """Consulta nomes metadades (sense descarregar) i retorna la durada en segons, o None."""
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
    """Baixa nomes el tram [inici, inici+durada_tros] del video, sense baixar-lo sencer."""
    fi = inici + durada_tros
    cmd = (
        f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]/best[ext=mp4]/best" '
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

TRACKS_RAW = os.environ.get('TRACKS', '')
print("Carregant tracks rebuts...")
tracks = json.loads(TRACKS_RAW)
for t in tracks:
    if t.get('timestamp_manual') not in (None, '', 0):
        t['timestamp_manual'] = float(t['timestamp_manual'])
    else:
        t['timestamp_manual'] = None

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

print(f"\nTracks ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")

print("\nObtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify")

titol_l1 = f"IF YOU KNOW ALL {len(tracks)}"
titol_l2 = f"YOU\u2019RE A REAL {FANOF.upper()} FAN"
subtitol = f"PART {PART}"

# ---------- Video generic de fons (opcional): cada clip agafa un tram diferent i aleatori ----------
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
            durada_track = DURADA_TOP1 if track['pos'] == 1 else DURADA_CLIP
            marge_bucket = max(0, bucket - durada_track)
            inici_bucket = usable_inici + i * bucket
            offset = inici_bucket + random.uniform(0, marge_bucket)
            offsets_fons[track['pos']] = max(0, min(offset, durada_fons_total - durada_track - 0.5))
        print(f"   Trams assignats a {n} clips (~{bucket:.0f}s per clip disponibles)")
    else:
        print(f"   AVIS: no s'ha pogut consultar la durada, es descarta el video de fons")
        FONS_URL = ''

clips_paths = []

max_pos = max(t['pos'] for t in tracks)
if PROVA_FOLLOW_MIG:
    print("\nPROVA ACTIVA: logo a baix + Follow/Thanks a la meitat del video")
elif STICKER_ACTIU:
    print(f"\nStickers Follow/Thanks actius, apareixeran al primer clip (#{max_pos})")

for track in tracks:
    pos              = track['pos']
    nom              = track['nom']
    artista          = track.get('artista', '')
    yt_url           = track.get('yt_url')
    timestamp_manual = track.get('timestamp_manual')
    nom_manual       = track.get('nom_manual')
    nivell           = track.get('nivell') or NIVELL_DEFAULT.get(pos, 'MEDIUM')
    nivell_color     = NIVELLS.get(nivell, COLOR_ACCENT)
    durada           = DURADA_TOP1 if pos == 1 else DURADA_CLIP
    es_ultim         = (pos == 1)
    es_primer        = (pos == max_pos)

    print(f"\nClip #{pos}: {nom} - {artista} [{nivell}]")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/videos/{pos:02d}.wav")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    cover_manual = track.get('cover_manual')
    cover_none   = track.get('cover_none', False)

    if cover_manual and cover_manual.startswith('http'):
        try:
            cover_data = requests.get(cover_manual, timeout=30).content
            if cover_data and len(cover_data) > 500:
                with open(thumb_path, 'wb') as f:
                    f.write(cover_data)
                print(f"   Portada manual OK ({cover_manual})")
        except Exception as e:
            print(f"   ERROR descarregant portada manual: {e}")
    elif cover_manual and os.path.exists(cover_manual) and os.path.getsize(cover_manual) > 1000:
        shutil.copy(cover_manual, thumb_path)
        print(f"   Portada manual OK ({cover_manual})")
    elif not cover_none:
        if COVER_FONT == 'youtube':
            cover_data = get_youtube_thumbnail(yt_url)
            if cover_data:
                with open(thumb_path, 'wb') as f:
                    f.write(cover_data)
                print(f"   Portada YouTube OK")
            else:
                print(f"   Sense miniatura de YouTube disponible")
        else:
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
                print(f"   Portada de l'artista a Spotify OK (fallback)")
    else:
        print(f"   Sense portada (marcat manualment)")

    if yt_url:
        font = yt_url
        print(f"   URL manual: {yt_url}")
    else:
        font = f"ytsearch1:{artista} {nom} official video"
        print(f"   Cerca: {artista} {nom}")
    ret = os.system(f'yt-dlp -f "{YTDLP_FORMAT}" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   No s'ha trobat videoclip - usant portada")
        output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
        if os.path.exists(thumb_path):
            os.system(f'ffmpeg -loop 1 -i "{thumb_path}" -f lavfi -i anullsrc=r=44100:cl=stereo -t {durada} -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" {VIDEO_OPTS} -r 30 -c:a aac -b:a 192k -ar 44100 -shortest "{output_path}" -y -loglevel error')
        else:
            os.system(f'ffmpeg -f lavfi -i color=c=black:s=1080x1920:d={durada} -f lavfi -i anullsrc=r=44100:cl=stereo -t {durada} -r 30 {VIDEO_OPTS} -c:a aac -b:a 192k -ar 44100 -shortest "{output_path}" -y -loglevel error')
        clips_paths.append((pos, output_path))
        continue

    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path], capture_output=True, text=True)
    info = json.loads(r.stdout)
    duracio_total = float(info['format']['duration'])
    for s in info.get('streams', []):
        if s.get('codec_type') == 'video':
            print(f"   Resolucio: {s.get('width')}x{s.get('height')}")
            break

    os.system(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{audio_path}" -y -loglevel error')

    if timestamp_manual is not None:
        inici = float(timestamp_manual)
        print(f"   Timestamp manual: {int(inici//60):02d}:{int(inici%60):02d}")
    else:
        inici = trobar_moment_impactant(audio_path, duracio_total, ESTIL) if os.path.exists(audio_path) else 30.0

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"

    nom = nom_manual if nom_manual else nom
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')
    nom_linia1, nom_linia2 = partir_nom(nom_net, max_chars=22)
    artista_net = artista.replace("'", "").replace('"', '').replace(':', '-')[:34]

    n_total = len(tracks)
    bar_progress = int(BAR_W * (n_total - pos + 1) / n_total)

    txt = []
    txt.append(f"drawbox=x=0:y=0:w=1080:h=440:color=black@0.24:t=fill")
    txt.append(f"drawbox=x=0:y=1580:w=1080:h=340:color=black@0.18:t=fill")
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol_l1}':fontsize=64:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol_l2}':fontsize=52:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1B}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{subtitol}':fontsize=32:fontcolor=white@0.85:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_TITOL2}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='#{pos}':fontsize=130:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=3:x={X_INFO}:y={Y_NUM}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_linia1}':fontsize=56:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM1}")
    if nom_linia2:
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_linia2}':fontsize=56:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM2}")
    # Etiqueta de nivell amb color
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='LEVEL\\: {nivell}':fontsize=48:fontcolor={nivell_color}:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={BAR_X}:y={Y_NIVELL}")
    txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='{artista_net}':fontsize=38:fontcolor=white@0.85:borderw=2:bordercolor=black@0.8:shadowx=0:shadowy=2:x={BAR_X}:y={Y_ARTISTA}")
    txt.append(f"drawbox=x={BAR_X}:y={Y_BAR}:w={BAR_W}:h=5:color=white@0.15:t=fill")
    txt.append(f"drawbox=x={BAR_X}:y={Y_BAR}:w={bar_progress}:h=5:color={nivell_color}@0.9:t=fill")

    if es_ultim:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=50:fontcolor=white@0.82:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_OUTRO}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='Electronic Vibes Daily':fontsize=30:fontcolor={COLOR_ACCENT}@0.70:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y={Y_OUTRO2}:enable='gte(t,{t_aparicio})'")

    txt_str = ",".join(txt)
    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    # Imatge: video generic de fons (si s'ha indicat); l'audio sempre surt del tema real
    usar_fons = bool(FONS_URL) and pos in offsets_fons
    fons_path = None
    if usar_fons:
        fons_path = os.path.expanduser(f"~/videos/{pos:02d}_fons.mp4")
        offset_fons = offsets_fons[pos]
        inici_baixada = max(0, offset_fons - PADDING_FONS)
        durada_baixada = durada + 2 * PADDING_FONS
        ok_fons = baixar_tros_fons(FONS_URL, inici_baixada, durada_baixada, fons_path)
        if ok_fons:
            print(f"   Tram de fons OK ({int(offset_fons//60):02d}:{int(offset_fons%60):02d})")
        else:
            print(f"   AVIS: no s'ha pogut baixar el tram de fons, s'usa el video de la canco")
            usar_fons = False
            fons_path = None

    input_parts = [f'-ss {inici} -i "{video_path}"']
    audio_idx = 0
    visual_idx = 0
    seguent_idx = 1

    if usar_fons and fons_path:
        offset_dins_tros = min(PADDING_FONS, offset_fons)
        input_parts.append(f'-ss {offset_dins_tros:.2f} -i "{fons_path}"')
        visual_idx = seguent_idx
        seguent_idx += 1

    thumb_idx = None
    if has_thumb:
        input_parts.append(f'-i "{thumb_path}"')
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
    if has_thumb:
        fc_parts.append(
            f"[{thumb_idx}:v]scale={COVER_W}:{COVER_H}:force_original_aspect_ratio=decrease,"
            f"pad={COVER_W}:{COVER_H}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[cover]"
        )
        fc_parts.append(f"[bg][cover]overlay={COVER_X}:{COVER_Y}[withcover]")
        fc_parts.append("[withcover]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    else:
        fc_parts.append("[bg]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    fc_parts.append(f"[colored]{txt_str},setpts=PTS/{SPEED_FACTOR}[txted]")
    fc_parts.append(f"[{audio_idx}:a]atempo={SPEED_FACTOR}[aout]")

    if es_primer and STICKER_PER_CLIP:
        fc_parts.append(
            f"[{sticker_follow_idx}:v]scale={STICKER_W}:-1,format=rgba,"
            f"fade=t=in:st=2.0:d=0.3:alpha=1,fade=t=out:st=3.8:d=0.3:alpha=1[stfollow]"
        )
        fc_parts.append(
            f"[{sticker_thanks_idx}:v]scale={STICKER_W}:-1,format=rgba,"
            f"fade=t=in:st=3.8:d=0.3:alpha=1,fade=t=out:st=5.3:d=0.3:alpha=1[stthanks]"
        )
        fc_parts.append(f"[txted][stfollow]overlay=(W-w)/2:{STICKER_Y}:enable='between(t,2.0,4.1)'[stk1]")
        fc_parts.append(f"[stk1][stthanks]overlay=(W-w)/2:{STICKER_Y}:enable='between(t,3.8,5.6)'[out]")
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

    os.system(cmd)
    clips_paths.append((pos, output_path))
    print(f"   OK clip generat")

clips_paths.sort(key=lambda x: x[0], reverse=True)
clips_valids = []
for pos, path in clips_paths:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        clips_valids.append(path)

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
offset = durades[0] - FADE_DURADA
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
output_final = f"{OUTPUT}/iconic_final.mp4"
cmd = f'ffmpeg {inputs_str}{extra_inputs} -filter_complex "{filter_complex}" -map "{mapa_video}" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 192k {limit_durada} "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
