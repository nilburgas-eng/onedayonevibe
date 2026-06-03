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
PADDING_X         = 80
Y_TITOL1          = 180
Y_TITOL2          = 260
Y_BASE            = 380

tracks = json.loads(TRACKS_RAW)

# ── SPOTIFY TOKEN ──
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
            img_data = requests.get(img_url).content
            return img_data
    except:
        pass
    return None

print("Obtenint token de Spotify...")
spotify_token = get_spotify_token()
if spotify_token:
    print("Token OK")
else:
    print("Token Spotify no disponible — sense portades")

def adaptar_font(text, mida_base=48, max_chars_base=22):
    chars = len(text)
    if chars <= max_chars_base: return mida_base
    elif chars <= 30: return int(mida_base * 0.85)
    elif chars <= 38: return int(mida_base * 0.70)
    else: return int(mida_base * 0.58)

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
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    # Portada oficial de Spotify
    if spotify_token:
        cover_data = get_spotify_cover(nom, ARTISTA, spotify_token)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada Spotify OK")

    # Si no hi ha portada Spotify, agafem la de YouTube
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        thumb_base = os.path.expanduser(f"~/videos/{pos:02d}_thumb")
        query = f"{ARTISTA} {nom} official video"
        os.system(f'yt-dlp --write-thumbnail --skip-download --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{thumb_base}" "ytsearch1:{query}" -q 2>/dev/null')
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
    if len(nom_net) > 45:
        nom_net = nom_net[:42].rsplit(' ', 1)[0] + '...'

    streams_net = str(streams).replace("'", "")
    daily_net = str(daily).replace("'", "")

    txt = []
    txt.append("drawtext=fontfile='" + FONT_BEBAS + "':text='" + titol1 + "':fontsize=72:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.35:shadowx=0:shadowy=2:x=(w-text_w)/2:y=" + str(Y_TITOL1))
    txt.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + titol2 + "':fontsize=38:fontcolor=0x00BFFF:borderw=1:bordercolor=black@0.8:x=(w-text_w)/2:y=" + str(Y_TITOL2))
    txt.append("drawtext=fontfile='" + FONT_EXTRABOLD + "':text='#" + str(pos) + "':fontsize=100:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.5:shadowx=0:shadowy=3:x=" + str(PADDING_X) + ":y=" + str(Y_BASE))
    txt.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + nom_net + "':fontsize=" + str(mida_nom) + ":fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.4:shadowx=0:shadowy=2:x=" + str(PADDING_X) + ":y=" + str(Y_BASE + 620))
    txt.append("drawtext=fontfile='" + FONT_EXTRABOLD + "':text='" + streams_net + " Spotify streams':fontsize=36:fontcolor=0x1DB954:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.4:shadowx=0:shadowy=2:x=" + str(PADDING_X) + ":y=" + str(Y_BASE + 680))
    txt.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + daily_net + " daily streams':fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.3:shadowx=0:shadowy=1:x=" + str(PADDING_X) + ":y=" + str(Y_BASE + 728))

    if pos == 1:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + compte_text + "':fontsize=54:fontcolor=white@0.85:shadowcolor=black@0.25:shadowx=0:shadowy=2:x=(w-text_w)/2:y=(h/2)+180:enable='gte(t," + str(t_aparicio) + ")'")
        txt.append("drawtext=fontfile='" + FONT_MEDIUM + "':text='Electronic Vibes Daily':fontsize=30:fontcolor=0x00BFFF@0.75:shadowcolor=black@0.20:shadowx=0:shadowy=1:x=(w-text_w)/2:y=(h/2)+248:enable='gte(t," + str(t_aparicio) + ")'")

    txt_str = ",".join(txt)
    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    if has_thumb:
        # Vídeo de fons difuminat + portada centrada gran + text a sota
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=30:5[bg];"
            "[1:v]scale=700:700:force_original_aspect_ratio=decrease,"
            "pad=700:700:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[cover];"
            "[bg][cover]overlay=(W-w)/2:" + str(Y_BASE) + "[withcover];"
            "[withcover]fps=30,colorchannelmixer=ra=0.85:ga=0.85:ba=0.85[colored];"
            "[colored]" + txt_str + "[out]"
        )
        cmd = f'ffmpeg -ss {inici} -i "{video_path}" -i "{thumb_path}" -t {durada} -filter_complex "{fc}" -map "[out]" -map 0:a -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'
    else:
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=25:5[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "setsar=1,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
            "[base]colorchannelmixer=ra=0.85:ga=0.85:ba=0.85[colored];"
            "[colored]" + txt_str + "[out]"
        )
        cmd = f'ffmpeg -ss {inici} -i "{video_path}" -t {durada} -filter_complex "{fc}" -map "[out]" -map 0:a -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'

    os.system(cmd)
    clips_paths.append((pos, output_path))
    print(f"   OK clip generat")

# Verificar clips
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
