import os, json, re, glob, shutil, subprocess, time
import librosa, numpy as np
from scipy.signal import find_peaks, butter, filtfilt
from datetime import datetime

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

ARTISTA    = os.environ['ARTISTA']
TRACKS_RAW = os.environ['TRACKS']
COMPTE     = "@onedayonevibe"
DURADA_CLIP   = 5
DURADA_TOP1   = 10
DURADA_OUTRO  = 2.0
FADE_DURADA   = 0.3
PADDING_X     = 100
Y_TITOL1      = 220
Y_TITOL2      = 300
Y_BASE        = 420
Y_SEP         = 78

tracks = json.loads(TRACKS_RAW)

def formatar_streams(n):
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    elif n >= 1_000_000:
        return f"{n/1_000_000:.0f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)

def trobar_moment_impactant(audio_path, duracio_total):
    try:
        audio, sr = librosa.load(audio_path, sr=22050, mono=True)
        hop_length = 512

        # Saltem els primers 30 segons per evitar intros i logos
        inici_cerca = min(30, duracio_total * 0.2)
        inici_sample = int(inici_cerca * sr)
        audio_tall = audio[inici_sample:]

        rms = librosa.feature.rms(y=audio_tall, frame_length=2048, hop_length=hop_length)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        rms_smooth = np.convolve(rms, np.ones(50)/50, mode='same')

        nyq = sr / 2
        b_low, a_low = butter(4, 100/nyq, btype='low')
        audio_sub = filtfilt(b_low, a_low, audio_tall)
        rms_sub = librosa.feature.rms(y=audio_sub, frame_length=2048, hop_length=hop_length)[0]
        rms_sub_smooth = np.convolve(rms_sub, np.ones(50)/50, mode='same')

        llindar = np.max(rms_smooth) * 0.7
        candidats, _ = find_peaks(rms_smooth, height=llindar, distance=sr//hop_length*15)
        if len(candidats) == 0:
            candidats = [np.argmax(rms_smooth)]

        millor = max(candidats, key=lambda i: rms_sub_smooth[i])
        moment = max(inici_cerca, inici_cerca + times[millor] - 2)
        print(f"   Moment impactant: {int(moment//60):02d}:{int(moment%60):02d}")
        return moment
    except Exception as e:
        print(f"   Error detecció: {e}")
        return 30.0

clips_paths = []

for track in tracks:
    pos      = track['pos']
    nom      = track['nom']
    streams  = track['streams']
    daily    = track['daily']
    durada   = DURADA_TOP1 if pos == 1 else DURADA_CLIP

    print(f"\n🎬 #{pos}: {nom}")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/videos/{pos:02d}.wav")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    # Descarregar videoclip oficial
    query = f"{ARTISTA} {nom} official video"
    print(f"   Buscant: {query}")
    ret = os.system(f'yt-dlp -f "best[ext=mp4]/best" --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "ytsearch1:{query}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   ⚠️ No s'ha trobat videoclip — usant portada")
        thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
        os.system(f'yt-dlp --write-thumbnail --skip-download --cookies cookies.txt -o "{os.path.expanduser(f"~/videos/{pos:02d}_thumb")}" "ytsearch1:{query}" -q')
        output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
        if os.path.exists(thumb_path):
            os.system(f'ffmpeg -loop 1 -i "{thumb_path}" -t {durada} -vf "scale=1920:1080,zoompan=z=\'min(zoom+0.001,1.3)\':x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':d={durada*25}:s=1080x1920,fps=30" -c:v libx264 -r 30 -c:a aac -ar 44100 "{output_path}" -y -loglevel error')
        else:
            os.system(f'ffmpeg -f lavfi -i color=c=black:s=1080x1920:d={durada} -r 30 -c:v libx264 -c:a aac -ar 44100 "{output_path}" -y -loglevel error')
        clips_paths.append((pos, output_path))
        continue

    # Obtenir duració del vídeo
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path], capture_output=True, text=True)
    duracio_total = float(json.loads(r.stdout)['format']['duration'])

    # Extreure audio per detectar moment
    os.system(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{audio_path}" -y -loglevel error')
    inici = trobar_moment_impactant(audio_path, duracio_total) if os.path.exists(audio_path) else 30.0

    # Generar clip
    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
    titol1 = f"TOP 10 {ARTISTA.upper()} SONGS"
    titol2 = "SPOTIFY STREAMS"
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')[:28]
    streams_net = str(streams).replace("'", "")
    daily_net = str(daily).replace("'", "")

    filtres = []

    # Títol
    filtres.append("drawtext=fontfile='" + FONT_BEBAS + "':text='" + titol1 + "':fontsize=72:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.35:shadowx=0:shadowy=2:x=(w-text_w)/2:y=" + str(Y_TITOL1))
    filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + titol2 + "':fontsize=38:fontcolor=0x00BFFF:borderw=1:bordercolor=black@0.8:x=(w-text_w)/2:y=" + str(Y_TITOL2))

    # Número gran
    filtres.append("drawtext=fontfile='" + FONT_EXTRABOLD + "':text='#" + str(pos) + "':fontsize=120:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.5:shadowx=0:shadowy=3:x=" + str(PADDING_X) + ":y=" + str(Y_BASE))

    # Nom cançó
    filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + nom_net + "':fontsize=48:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.4:shadowx=0:shadowy=2:x=" + str(PADDING_X) + ":y=" + str(Y_BASE + 130))

    # Streams totals — més visibles
    filtres.append("drawtext=fontfile='" + FONT_EXTRABOLD + "':text='" + streams_net + " Spotify streams':fontsize=36:fontcolor=0x1DB954:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.4:shadowx=0:shadowy=2:x=" + str(PADDING_X) + ":y=" + str(Y_BASE + 190))

    # Streams diaris — més visibles
    filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + daily_net + " daily streams':fontsize=30:fontcolor=white:borderw=2:bordercolor=black@0.9:shadowcolor=black@0.3:shadowx=0:shadowy=1:x=" + str(PADDING_X) + ":y=" + str(Y_BASE + 238))

    # Outro al clip #1
    if pos == 1:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + compte_text + "':fontsize=54:fontcolor=white@0.85:shadowcolor=black@0.25:shadowx=0:shadowy=2:x=(w-text_w)/2:y=(h/2)+180:enable='gte(t," + str(t_aparicio) + ")'")
        filtres.append("drawtext=fontfile='" + FONT_MEDIUM + "':text='Electronic Vibes Daily':fontsize=30:fontcolor=0x00BFFF@0.75:shadowcolor=black@0.20:shadowx=0:shadowy=1:x=(w-text_w)/2:y=(h/2)+248:enable='gte(t," + str(t_aparicio) + ")'")

    vf = ",".join(filtres)
    cmd = f'ffmpeg -ss {inici} -i "{video_path}" -t {durada} -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,setsar=1,fps=30,colorchannelmixer=ra=0.85:ga=0.85:ba=0.85,{vf}" -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'
    os.system(cmd)
    clips_paths.append((pos, output_path))
    print(f"   ✅ Clip generat")

# Ordenar clips del 10 al 1
clips_paths.sort(key=lambda x: x[0], reverse=True)
clips_ordenats = [p for _, p in clips_paths]

# Muntar amb crossfade
print("\n🎬 Muntant vídeo final...")
durades = []
for path in clips_ordenats:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    d = float(json.loads(r.stdout)['format']['duration'])
    durades.append(d)

n_clips = len(clips_ordenats)
inputs_str = " ".join([f"-i '{p}'" for p in clips_ordenats])
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
print("✅ Video final generat!")
