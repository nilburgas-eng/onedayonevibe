import os, json, re, glob, shutil, subprocess, time, base64
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

ARTISTA           = os.environ['ARTISTA']
TRACKS_RAW        = os.environ['TRACKS']
ESTIL             = os.environ.get('ESTIL', 'energetic')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
COMPTE            = "@onedayonevibe"
DURADA_CLIP       = 5
DURADA_TOP1       = 10
DURADA_OUTRO      = 2.0
FADE_DURADA       = 0.3

# ── LAYOUT 1080x1920 ──
SAFE_TOP     = 160   # Zona segura TikTok
Y_TITOL1     = 160   # TOP 10 ARTISTA SONGS
Y_TITOL2     = 220   # SPOTIFY STREAMS
Y_COVER      = 270   # Portada (top)
COVER_SIZE   = 220   # Mida portada px
X_COVER      = 55    # X portada
X_INFO       = 320   # X info (dreta portada)
Y_NUM        = 340   # Número #X
Y_NOM        = 470   # Nom cançó
Y_STREAMS    = 550   # Streams Spotify
Y_DAILY      = 610   # Daily streams
Y_BAR        = 650   # Barra ranking
Y_OUTRO      = 1580  # @compte
Y_OUTRO2     = 1650  # Electronic Vibes Daily

tracks = json.loads(TRACKS_RAW)

def get_spotify_token():
    try:
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET}".encode()).decode()
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"}
        )
        return r.json().get('access_token')
    except:
        return None

def get_spotify_cover(nom_canco, artista, token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        query = f"track:{nom_canco} artist:{artista}"
        r = requests.get(
            f"https://api.spotify.com/v1/search?q={requests.utils.quote(query)}&type=track&limit=1",
            headers=headers
        )
        items = r.json().get('tracks', {}).get('items', [])
        if items:
            img_url = items[0]['album']['images'][0]['url']
            return requests.get(img_url).content
    except:
        pass
    return None

def adaptar_font(text, mida_base=120):
    chars = len(text)
    if chars <= 16: return mida_base
    elif chars <= 24: return int(mida_base * 0.80)
    elif chars <= 32: return int(mida_base * 0.65)
    else: return int(mida_base * 0.52)

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
        print(f"   Moment ({estil}): {int(moment//60):02d}:{int(moment%60):02d}")
        return moment
    except Exception as e:
        print(f"   Error deteccio: {e}")
        return 30.0

print("Obtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify")

clips_paths = []

for track in tracks:
    pos      = track['pos']
    nom      = track['nom']
    streams  = track['streams']
    daily    = track['daily']
    durada   = DURADA_TOP1 if pos == 1 else DURADA_CLIP

    print(f"\nClip #{pos}: {nom}")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/videos/{pos:02d}.wav")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
    thumb_base = os.path.expanduser(f"~/videos/{pos:02d}_thumb")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    # Portada Spotify oficial
    if spotify_token:
        cover_data = get_spotify_cover(nom, ARTISTA, spotify_token)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada Spotify OK")

    # Fallback YouTube
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        query_thumb = f"{ARTISTA} {nom} official video"
        os.system(f'yt-dlp --write-thumbnail --skip-download --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{thumb_base}" "ytsearch1:{query_thumb}" -q 2>/dev/null')
        thumb_webp = thumb_base + ".webp"
        if not os.path.exists(thumb_path) and os.path.exists(thumb_webp):
            os.system(f'ffmpeg -i "{thumb_webp}" "{thumb_path}" -y -loglevel error')

    # Descarregar videoclip
    query = f"{ARTISTA} {nom} official video"
    ret = os.system(f'yt-dlp -f "best[ext=mp4]/best" --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "ytsearch1:{query}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   No s'ha trobat videoclip — usant portada")
        output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
        if os.path.exists(thumb_path):
            os.system(f'ffmpeg -loop 1 -i "{thumb_path}" -t {durada} -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" -c:v libx264 -r 30 -c:a aac -ar 44100 "{output_path}" -y -loglevel error')
        else:
            os.system(f'ffmpeg -f lavfi -i color=c=black:s=1080x1920:d={durada} -r 30 -c:v libx264 -c:a aac -ar 44100 "{output_path}" -y -loglevel error')
        clips_paths.append((pos, output_path))
        continue

    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path], capture_output=True, text=True)
    duracio_total = float(json.loads(r.stdout)['format']['duration'])

    os.system(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{audio_path}" -y -loglevel error')
    inici = trobar_moment_impactant(audio_path, duracio_total, ESTIL) if os.path.exists(audio_path) else 30.0

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
    titol1 = f"TOP {len(tracks)} {ARTISTA.upper()} SONGS"
    titol2 = "SPOTIFY STREAMS"

    mida_nom = adaptar_font(nom)
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')
    if len(nom_net) > 40:
        nom_net = nom_net[:37].rsplit(' ', 1)[0] + '...'
    streams_net = str(streams).replace("'", "")
    daily_net = str(daily).replace("'", "")

    # Barra ranking
    n_total = len(tracks)
    bar_width = 700
    bar_progress = int(bar_width * (n_total - pos + 1) / n_total)

    txt = []
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol1}':fontsize=68:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.3:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{titol2}':fontsize=40:fontcolor=0x00BFFF:borderw=1:bordercolor=black@0.7:x=(w-text_w)/2:y={Y_TITOL2}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='#{pos}':fontsize=120:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.5:shadowx=0:shadowy=3:x={X_INFO}:y={Y_NUM}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_net}':fontsize={mida_nom}:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.4:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{streams_net} Spotify streams':fontsize=40:fontcolor=0x1DB954:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.3:shadowx=0:shadowy=2:x={X_INFO}:y={Y_STREAMS}")
    txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='{daily_net} daily streams':fontsize=34:fontcolor=white@0.70:borderw=1:bordercolor=black@0.8:x={X_INFO}:y={Y_DAILY}")
    txt.append(f"drawbox=x={X_COVER}:y={Y_BAR}:w={bar_width}:h=6:color=white@0.12:t=fill")
    txt.append(f"drawbox=x={X_COVER}:y={Y_BAR}:w={bar_progress}:h=6:color=0x1DB954@0.9:t=fill")

    if pos == 1:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=52:fontcolor=white@0.82:borderw=1:bordercolor=black@0.6:shadowcolor=black@0.2:x=(w-text_w)/2:y={Y_OUTRO}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='Electronic Vibes Daily':fontsize=32:fontcolor=0x00BFFF@0.72:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y={Y_OUTRO2}:enable='gte(t,{t_aparicio})'")

    txt_str = ",".join(txt)
    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    if has_thumb:
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bgfull];"
            "[bgfull]boxblur=8:2[bg];"
            "[1:v]scale={cs}:{cs}:force_original_aspect_ratio=decrease,"
            "pad={cs}:{cs}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[cover];"
            "[bg][cover]overlay={xc}:{yc}[withcover];"
            "[withcover]fps=30,colorchannelmixer=ra=0.85:ga=0.85:ba=0.85[colored];"
            "[colored]{txt}[out]"
        ).format(cs=COVER_SIZE, xc=X_COVER, yc=Y_COVER, txt=txt_str)
        cmd = f'ffmpeg -ss {inici} -i "{video_path}" -i "{thumb_path}" -t {durada} -filter_complex "{fc}" -map "[out]" -map 0:a -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'
    else:
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bgfull];"
            "[bgfull]boxblur=8:2[bg];"
            "[bg]fps=30,colorchannelmixer=ra=0.85:ga=0.85:ba=0.85[colored];"
            "[colored]{txt}[out]"
        ).format(txt=txt_str)
        cmd = f'ffmpeg -ss {inici} -i "{video_path}" -t {durada} -filter_complex "{fc}" -map "[out]" -map 0:a -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'

    os.system(cmd)
    clips_paths.append((pos, output_path))
    print(f"   OK clip generat")

# Verificar i muntar
clips_paths.sort(key=lambda x: x[0], reverse=True)
clips_valids = []
for pos, path in clips_paths:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        clips_valids.append(path)
    else:
        print(f"   Clip no valid: {path}")

if len(clips_valids) < 2:
    print("ERROR: No hi ha prou clips valids")
    exit(1)

print(f"\nMuntant video final amb {len(clips_valids)} clips...")
durades = []
for path in clips_valids:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    d = float(json.loads(r.stdout)['format']['duration'])
    durades.append(d)

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
output_final = f"{OUTPUT}/top10_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" -c:v libx264 -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
