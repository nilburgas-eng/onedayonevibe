import os, json, re, subprocess, base64
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
SETMANA_TEXT_ENV  = os.environ.get('SETMANA_TEXT', '')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
COMPTE            = "@onedayonevibe"
DURADA_CLIP       = 8
DURADA_TOP1       = 12
DURADA_OUTRO      = 2.0
FADE_DURADA       = 0.3

COLOR_ACCENT = "0x00BFFF"

COVER_W  = 280
COVER_H  = 280
COVER_X  = 90
COVER_Y  = 470
X_INFO   = 410
Y_NUM    = 470
Y_NOM1   = 610
Y_NOM2   = 680
Y_TITOL1 = 190
Y_TITOL2 = 268
Y_ARTISTA = 760
Y_BAR    = 850
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

def scrape_chart():
    url = "https://www.electricfm.com/music/weekly-top-20-chart"
    print(f"Scraping: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers).text

    # Data de la setmana: "Week of July 21, 2026"
    setmana_text = ""
    m = re.search(r'Week of ([A-Z][a-z]+ \d+, \d{4})', html)
    if m:
        setmana_text = f"WEEK OF {m.group(1).upper()}"

    # Treure tags i normalitzar
    net = re.sub(r'<[^>]+>', '\n', html)
    net = re.sub(r'&amp;', '&', net)
    net = re.sub(r'&#039;|&#39;', "'", net)
    net = re.sub(r'&quot;', '"', net)
    linies = [l.strip() for l in net.split('\n')]
    linies = [l for l in linies if l]

    # Cada cançó: "#N" seguit de TITOL i ARTISTA (repetits 2 cops)
    tracks = []
    vistos = set()
    i = 0
    while i < len(linies) and len(tracks) < 10:
        m_pos = re.match(r'^#(\d+)$', linies[i])
        if m_pos:
            pos_num = int(m_pos.group(1))
            # Les seguents linies no-buides: titol i artista
            resta = [l for l in linies[i+1:i+6] if l and not re.match(r'^#\d+$', l)]
            if len(resta) >= 2:
                nom = resta[0]
                artista = resta[1]
                key = (nom.lower(), artista.lower())
                if key not in vistos and pos_num <= 10:
                    vistos.add(key)
                    tracks.append({
                        'pos': pos_num, 'nom': nom, 'artista': artista,
                        'timestamp_manual': None, 'nom_manual': None, 'yt_url': None
                    })
        i += 1

    tracks.sort(key=lambda t: t['pos'])
    return tracks, setmana_text

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

# TRACKS manual o scraping
TRACKS_RAW = os.environ.get('TRACKS', '')
if TRACKS_RAW:
    print("Carregant tracks rebuts (manual)...")
    tracks = json.loads(TRACKS_RAW)
    setmana_text = SETMANA_TEXT_ENV
    for t in tracks:
        if t.get('timestamp_manual') not in (None, '', 0):
            t['timestamp_manual'] = float(t['timestamp_manual'])
        else:
            t['timestamp_manual'] = None
else:
    print("Scraping del chart...")
    tracks, setmana_text = scrape_chart()
    print(f"Setmana: {setmana_text}")

if not tracks:
    print("ERROR: No s'han trobat tracks")
    exit(1)

print(f"\nTracks ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")

print("\nObtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify")

clips_paths = []

for track in tracks:
    pos              = track['pos']
    nom              = track['nom']
    artista          = track.get('artista', '')
    yt_url           = track.get('yt_url')
    timestamp_manual = track.get('timestamp_manual')
    nom_manual       = track.get('nom_manual')
    durada           = DURADA_TOP1 if pos == 1 else DURADA_CLIP
    es_ultim         = (pos == 1)

    print(f"\nClip #{pos}: {nom} - {artista}")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/videos/{pos:02d}.wav")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    cover_url = track.get('cover_url')
    if cover_url:
        try:
            cover_data = requests.get(cover_url, timeout=15).content
            if cover_data and len(cover_data) > 1000:
                with open(thumb_path, 'wb') as f:
                    f.write(cover_data)
                print(f"   Portada directa OK")
        except:
            pass
    if (not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000) and spotify_token:
        cover_data = get_spotify_cover(nom, artista, spotify_token)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada Spotify OK")

    if yt_url:
        font = yt_url
        print(f"   URL manual: {yt_url}")
    else:
        font = f"ytsearch1:{artista} {nom} official video"
        print(f"   Cerca: {artista} {nom}")
    ret = os.system(f'yt-dlp -f "best[ext=mp4]/best" --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   No s'ha trobat videoclip - usant portada")
        output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
        if os.path.exists(thumb_path):
            os.system(f'ffmpeg -loop 1 -i "{thumb_path}" -f lavfi -i anullsrc=r=44100:cl=stereo -t {durada} -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 -shortest "{output_path}" -y -loglevel error')
        else:
            os.system(f'ffmpeg -f lavfi -i color=c=black:s=1080x1920:d={durada} -f lavfi -i anullsrc=r=44100:cl=stereo -t {durada} -r 30 -c:v libx264 -c:a aac -b:a 192k -ar 44100 -shortest "{output_path}" -y -loglevel error')
        clips_paths.append((pos, output_path))
        continue

    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path], capture_output=True, text=True)
    duracio_total = float(json.loads(r.stdout)['format']['duration'])

    os.system(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{audio_path}" -y -loglevel error')

    if timestamp_manual is not None:
        inici = float(timestamp_manual)
        print(f"   Timestamp manual: {int(inici//60):02d}:{int(inici%60):02d}")
    else:
        inici = trobar_moment_impactant(audio_path, duracio_total, ESTIL) if os.path.exists(audio_path) else 30.0

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
    titol1 = "ELECTRONIC MUSIC CHART"
    setmana_disp = setmana_text if setmana_text else "TOP 10 OF THE WEEK"

    nom = nom_manual if nom_manual else nom
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')
    nom_linia1, nom_linia2 = partir_nom(nom_net, max_chars=22)
    artista_net = artista.replace("'", "").replace('"', '').replace(':', '-')[:34]

    n_total = len(tracks)
    bar_progress = int(BAR_W * (n_total - pos + 1) / n_total)

    txt = []
    txt.append(f"drawbox=x=0:y=0:w=1080:h=380:color=black@0.22:t=fill")
    txt.append(f"drawbox=x=0:y=1580:w=1080:h=340:color=black@0.18:t=fill")
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol1}':fontsize=72:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{setmana_disp}':fontsize=32:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_TITOL2}")
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

    if has_thumb:
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920:(iw-1080)/2:(ih-1920)/2[bg];"
            "[1:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
            "pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1[cover];"
            "[bg][cover]overlay={cx}:{cy}[withcover];"
            "[withcover]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored];"
            "[colored]{txt}[out]"
        ).format(cw=COVER_W, ch=COVER_H, cx=COVER_X, cy=COVER_Y, txt=txt_str)
        cmd = f'ffmpeg -ss {inici} -i "{video_path}" -i "{thumb_path}" -t {durada} -filter_complex "{fc}" -map "[out]" -map 0:a -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'
    else:
        fc = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920:(iw-1080)/2:(ih-1920)/2[bg];"
            "[bg]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored];"
            "[colored]{txt}[out]"
        ).format(txt=txt_str)
        cmd = f'ffmpeg -ss {inici} -i "{video_path}" -t {durada} -filter_complex "{fc}" -map "[out]" -map 0:a -c:v libx264 -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'

    os.system(cmd)
    clips_paths.append((pos, output_path))
    print(f"   OK clip generat")

# Ordenar de #10 a #1 (clímax al #1 al final)
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
output_final = f"{OUTPUT}/chart_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" -c:v libx264 -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
