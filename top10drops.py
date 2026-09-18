import os, json, re, subprocess, base64, shutil, random
import librosa, numpy as np
from scipy.signal import find_peaks, butter, filtfilt
from PIL import ImageFont
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
TEMA_ENV          = os.environ.get('TEMA', '')
PART_ENV          = os.environ.get('PART', '')
COVER_FONT        = os.environ.get('COVER_FONT', 'spotify')   # 'spotify' o 'youtube'
FONS_URL          = os.environ.get('FONS_URL', '').strip()
MARGE_FONS        = 15.0   # segons a evitar al principi/final del video de fons
PADDING_FONS      = 1.0    # marge extra de seguretat al baixar cada tros
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
COMPTE            = "@onedayonevibe"
DURADA_CLIP       = 5
DURADA_TOP1       = 8
DURADA_OUTRO      = 2.0
FADE_DURADA       = 0.3

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"

SPEED_FACTOR = 1.03   # acceleracio subtil audio+video. 1.0 = desactivat

COLOR_ACCENT = "0x00BFFF"

COVER_W  = 280
COVER_H  = 280
COVER_X  = 90
COVER_Y  = 500
X_INFO   = 410
Y_NUM    = 500
Y_NOM1   = 640
Y_NOM2   = 710
Y_TITOL1  = 260
Y_TITOL1B = 330
Y_TITOL2  = 400
Y_ARTISTA = 790
Y_BAR    = 870
BAR_X    = 90
BAR_W    = 980
Y_OUTRO  = 1560
Y_OUTRO2 = 1618

LOGO_PATH    = "logo.png"
LOGO_W       = 140
LOGO_OPACITY = 0.95
LOGO_MARGIN  = 30
LOGO_ACTIU   = os.path.exists(LOGO_PATH)

AMPLE_MAX_TITOL    = 900   # marge de seguretat dins dels 1080px d'ample
AMPLE_MAX_SUBTITOL = 900
MIDES_TITOL        = [68, 62, 56, 50, 44, 38]
MIDES_SUBTITOL     = [32, 28, 25, 22]


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
    try:
        headers = {"Authorization": f"Bearer {token}"}
        query = f"artist:{artista}"
        r = requests.get(f"https://api.spotify.com/v1/search?q={requests.utils.quote(query)}&type=artist&limit=1", headers=headers)
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

def amplada_text(text, font_path, mida):
    try:
        font = ImageFont.truetype(font_path, mida)
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * mida * 0.55

def ajustar_text(text, font_path, ample_max, mides):
    """Retorna (mida_font, [linies]) ajustant la mida i partint en 2 linies si cal."""
    text = text.strip()
    for mida in mides:
        if amplada_text(text, font_path, mida) <= ample_max:
            return mida, [text]

    mida_min = mides[-1]
    paraules = text.split(' ')
    if len(paraules) < 2:
        return mida_min, [text]

    millor = None
    for idx in range(1, len(paraules)):
        l1 = ' '.join(paraules[:idx])
        l2 = ' '.join(paraules[idx:])
        ample1 = amplada_text(l1, font_path, mida_min)
        ample2 = amplada_text(l2, font_path, mida_min)
        diferencia = abs(ample1 - ample2)
        if millor is None or diferencia < millor[0]:
            millor = (diferencia, l1, l2, max(ample1, ample2))
    _, l1, l2, ample_pitjor = millor

    for mida in mides:
        if amplada_text(l1, font_path, mida) <= ample_max and amplada_text(l2, font_path, mida) <= ample_max:
            return mida, [l1, l2]
    return mida_min, [l1, l2]

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

print(f"\nFont de portades: {COVER_FONT}")
print("Obtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify")

titol_complet = f"TOP 10 {TEMA_ENV.upper()} DROPS".replace("  ", " ").strip() if TEMA_ENV else "TOP 10 DROPS"
subtitol_complet = f"PART {PART_ENV}" if PART_ENV else ''

mida_titol, linies_titol = ajustar_text(titol_complet, FONT_BEBAS, AMPLE_MAX_TITOL, MIDES_TITOL)
titol_l1 = linies_titol[0]
titol_l2 = linies_titol[1] if len(linies_titol) > 1 else None
mida_subtitol, linies_subtitol = ajustar_text(subtitol_complet, FONT_SEMIBOLD, AMPLE_MAX_SUBTITOL, MIDES_SUBTITOL) if subtitol_complet else (28, [''])
subtitol_disp = linies_subtitol[0]

print(f"Titol: '{titol_l1}'" + (f" / '{titol_l2}'" if titol_l2 else "") + f" (mida {mida_titol})")
print(f"Subtitol: '{subtitol_disp}' (mida {mida_subtitol})")

offsets_fons = {}
if FONS_URL:
    print(f"\nVideo de fons compartit: {FONS_URL}")
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

for track in tracks:
    pos              = track['pos']
    nom              = track['nom']
    artista          = track.get('artista', '')
    yt_url           = track.get('yt_url')
    video_manual     = track.get('video_manual')
    timestamp_manual = track.get('timestamp_manual')

    es_ultim = (pos == 1)
    durada = DURADA_TOP1 if es_ultim else DURADA_CLIP
    if es_ultim:
        durada += DURADA_OUTRO

    video_path = os.path.expanduser(f"~/video_{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/audio_{pos:02d}.wav")
    thumb_path = os.path.expanduser(f"~/thumb_{pos:02d}.jpg")

    print(f"\n--- #{pos}: {nom} - {artista} ---")

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
            elif spotify_token:
                cover_data = get_spotify_cover(nom, artista, spotify_token)
                if cover_data:
                    with open(thumb_path, 'wb') as f:
                        f.write(cover_data)
                    print(f"   Portada Spotify OK (fallback)")
        else:
            cover_data = get_spotify_cover(nom, artista, spotify_token) if spotify_token else None
            if cover_data:
                with open(thumb_path, 'wb') as f:
                    f.write(cover_data)
                print(f"   Portada Spotify OK")
            else:
                cover_data = get_youtube_thumbnail(yt_url)
                if cover_data:
                    with open(thumb_path, 'wb') as f:
                        f.write(cover_data)
                    print(f"   Portada YouTube OK (fallback)")

        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
            if spotify_token:
                cover_data = get_spotify_artist_image(artista, spotify_token)
                if cover_data:
                    with open(thumb_path, 'wb') as f:
                        f.write(cover_data)
                    print(f"   Portada Spotify artista OK (fallback)")

        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
            print(f"   AVIS: cap portada trobada per aquest track")
    else:
        print(f"   Sense portada (marcat manualment)")

    if video_manual:
        print(f"   Video manual: {video_manual}")
        if video_manual.startswith('http'):
            ret = 1
            try:
                r = requests.get(video_manual, timeout=180, stream=True)
                if r.status_code == 200:
                    with open(video_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    if os.path.getsize(video_path) > 10000:
                        ret = 0
                    else:
                        print(f"   ERROR: video manual descarregat buit")
                else:
                    print(f"   ERROR descarregant video manual: HTTP {r.status_code}")
            except Exception as e:
                print(f"   ERROR descarregant video manual: {e}")
        elif os.path.exists(video_manual) and os.path.getsize(video_manual) > 10000:
            shutil.copy(video_manual, video_path)
            ret = 0
        else:
            print(f"   ERROR: no s'ha trobat {video_manual}")
            ret = 1
    elif yt_url:
        font = yt_url
        print(f"   URL manual: {yt_url}")
        ret = os.system(f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font}" --no-playlist -q')
    else:
        font = f"ytsearch1:{artista} {nom} official video"
        print(f"   Cerca: {artista} {nom}")
        ret = os.system(f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font}" --no-playlist -q')

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
            print(f"   RESOLUCIO BAIXADA: {s.get('width')}x{s.get('height')}")
            break

    os.system(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{audio_path}" -y -loglevel error')

    if timestamp_manual is not None:
        inici = float(timestamp_manual)
        print(f"   Timestamp manual: {int(inici//60):02d}:{int(inici%60):02d}")
    else:
        inici = trobar_moment_impactant(audio_path, duracio_total, ESTIL) if os.path.exists(audio_path) else 30.0

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"

    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')
    nom_linia1, nom_linia2 = partir_nom(nom_net, max_chars=22)
    artista_net = artista.replace("'", "").replace('"', '').replace(':', '-')[:34]

    n_total = len(tracks)
    bar_progress = int(BAR_W * (n_total - pos + 1) / n_total)

    titol_l1_net = titol_l1.replace("'", "").replace('"', '')
    titol_l2_net = titol_l2.replace("'", "").replace('"', '') if titol_l2 else None
    subtitol_net = subtitol_disp.replace("'", "").replace('"', '')

    txt = []
    txt.append(f"drawbox=x=0:y=0:w=1080:h=440:color=black@0.24:t=fill")
    txt.append(f"drawbox=x=0:y=1580:w=1080:h=340:color=black@0.18:t=fill")
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol_l1_net}':fontsize={mida_titol}:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    if titol_l2_net:
        txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol_l2_net}':fontsize={mida_titol}:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1B}")
    if subtitol_net:
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{subtitol_net}':fontsize={mida_subtitol}:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_TITOL2}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='#{pos}':fontsize=130:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=3:x={X_INFO}:y={Y_NUM}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_linia1}':fontsize=56:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM1}")
    if nom_linia2:
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_linia2}':fontsize=56:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM2}")
    txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='{artista_net}':fontsize=40:fontcolor=white@0.85:borderw=2:bordercolor=black@0.8:shadowx=0:shadowy=2:x={BAR_X}:y={Y_ARTISTA}")
    txt.append(f"drawbox=x={BAR_X}:y={Y_BAR}:w={BAR_W}:h=5:color=white@0.15:t=fill")
    txt.append(f"drawbox=x={BAR_X}:y={Y_BAR}:w={bar_progress}:h=5:color={COLOR_ACCENT}@0.9:t=fill")

    if es_ultim:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=50:fontcolor=white@0.82:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_OUTRO}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='Electronic Vibes Daily':fontsize=30:fontcolor={COLOR_ACCENT}@0.70:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y={Y_OUTRO2}:enable='gte(t,{t_aparicio})'")

    txt_str = ",".join(txt)
    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    usar_fons = bool(FONS_URL) and not video_manual and pos in offsets_fons
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
    if LOGO_ACTIU:
        input_parts.append(f'-i "{LOGO_PATH}"')
        logo_idx = seguent_idx
        seguent_idx += 1

    inputs = " ".join(input_parts)

    fc_parts = [
        f"[{visual_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2[bg]"
    ]
    if has_thumb:
        fc_parts.append(
            f"[{thumb_idx}:v]scale={COVER_W}:{COVER_H}:force_original_aspect_ratio=decrease,"
            f"pad={COVER_W}:{COVER_H}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[cover]"
        )
        fc_parts.append(f"[bg][cover]overlay={COVER_X}:{COVER_Y}[withcover]")
        fc_parts.append("[withcover]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    else:
        fc_parts.append("[bg]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    fc_parts.append(f"[colored]{txt_str},setpts=PTS/{SPEED_FACTOR}[out]")
    fc_parts.append(f"[{audio_idx}:a]atempo={SPEED_FACTOR}[aout]")

    if LOGO_ACTIU:
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

filter_complex = ";".join(video_filters + audio_filters)
output_final = f"{OUTPUT}/top10drops_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
