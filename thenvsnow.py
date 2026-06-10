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
ANY_TALL          = int(os.environ.get('ANY_TALL', '2018'))
ESTIL             = os.environ.get('ESTIL', 'energetic')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
LASTFM_API_KEY    = os.environ.get('LASTFM_API_KEY', '')
COMPTE            = "@onedayonevibe"
DURADA_CLIP       = 8
DURADA_OUTRO      = 2.0
FADE_DURADA       = 0.3

COLOR_THEN = "0x00BFFF"
COLOR_NOW  = "0xFF6B00"

COVER_W  = 280
COVER_H  = 280
COVER_X  = 90
COVER_Y  = 420
X_INFO   = 410
Y_NUM    = 420
Y_NOM1   = 560
Y_NOM2   = 630
Y_TITOL1 = 210
Y_TITOL2 = 285
Y_ANY    = 740
Y_BAR    = 790
BAR_X    = 90
BAR_W    = 980
Y_OUTRO  = 1500
Y_OUTRO2 = 1558
Y_OUTRO3 = 1620

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

def buscar_tracks_lastfm(artista, any_tall, api_key):
    print("Buscant tracks via Last.fm...")
    try:
        r = requests.get(
            f"https://ws.audioscrobbler.com/2.0/?method=artist.gettoptracks&artist={requests.utils.quote(artista)}&api_key={api_key}&format=json&limit=50"
        )
        data = r.json()
        top_tracks = data.get('toptracks', {}).get('track', [])
        print(f"Top tracks Last.fm: {len(top_tracks)}")

        if not top_tracks:
            return []

        # Deduplicar per nom normalitzat (sense parèntesis/claudàtors)
        # mantenint l'ordre de popularitat de Last.fm
        tracks_amb_any = []
        vistes = set()

        for t in top_tracks[:30]:
            nom = t['name']
            key_norm = re.sub(r'\s*[\(\[].*?[\)\]]', '', nom.lower()).strip()
            if key_norm in vistes:
                continue
            vistes.add(key_norm)

            # Any via MusicBrainz
            any_canco = 0
            try:
                mb = requests.get(
                    f"https://musicbrainz.org/ws/2/recording/?query=recording:{requests.utils.quote(nom)}+artist:{requests.utils.quote(artista)}&fmt=json&limit=1",
                    headers={"User-Agent": "onedayonevibe/1.0 (nilburgas@gmail.com)"}
                )
                recordings = mb.json().get('recordings', [])
                if recordings:
                    date = recordings[0].get('first-release-date', '')
                    if date:
                        any_canco = int(date[:4])
                time.sleep(0.3)
            except:
                pass

            tracks_amb_any.append({'nom': nom, 'any': any_canco})

        # Classificar (mantenen ordre de popularitat)
        then_list = [t for t in tracks_amb_any if 0 < t['any'] < any_tall]
        now_list  = [t for t in tracks_amb_any if t['any'] >= any_tall]

        # Si no hi ha anys, distribuir per ordre
        if not then_list and not now_list:
            mid = len(tracks_amb_any) // 2
            then_list = tracks_amb_any[:mid]
            now_list  = tracks_amb_any[mid:]
            print("Anys no disponibles — distribuint per ordre")

        # EQUILIBRI: igualar el nombre de THEN i NOW
        n = min(len(then_list), len(now_list), 5)
        if n == 0:
            # Una era buida: agafar el que hi hagi, max 10
            print(f"AVÍS: una era buida (THEN:{len(then_list)} NOW:{len(now_list)})")
            then_list = then_list[:5]
            now_list  = now_list[:5]
        else:
            then_list = then_list[:n]
            now_list  = now_list[:n]

        print(f"THEN: {len(then_list)} · NOW: {len(now_list)} (equilibrat a {n} cada un)")

        # Intercalar
        tracks = []
        pos = 1
        max_len = max(len(then_list), len(now_list))
        for i in range(max_len):
            if i < len(then_list) and len(tracks) < 10:
                tracks.append({
                    'pos': pos, 'nom': then_list[i]['nom'], 'any': then_list[i]['any'],
                    'era': 'THEN', 'streams': '', 'cover_url': None,
                    'timestamp_manual': None, 'nom_manual': None
                })
                pos += 1
            if i < len(now_list) and len(tracks) < 10:
                tracks.append({
                    'pos': pos, 'nom': now_list[i]['nom'], 'any': now_list[i]['any'],
                    'era': 'NOW', 'streams': '', 'cover_url': None,
                    'timestamp_manual': None, 'nom_manual': None
                })
                pos += 1

        return tracks

    except Exception as e:
        print(f"Error Last.fm: {e}")
        return []

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
            print(f"   Moment (vocal): {int(moment//60):02d}:{int(moment%60):02d}")
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
        print(f"   Moment ({estil}): {int(moment//60):02d}:{int(moment%60):02d}")
        return moment
    except Exception as e:
        print(f"   Error deteccio: {e}")
        return 30.0

print("Carregant tracks rebuts...")
TRACKS_RAW = os.environ.get('TRACKS', '')
tracks = json.loads(TRACKS_RAW)

# Convertir timestamp manual (segons) a float si existeix
for t in tracks:
    if t.get('timestamp_manual') not in (None, '', 0):
        t['timestamp_manual'] = float(t['timestamp_manual'])
    else:
        t['timestamp_manual'] = None

if not tracks:
    print("ERROR: No s'han rebut tracks")
    exit(1)

print(f"\nTracks seleccionats ({len(tracks)}):")
for t in tracks:
    print(f"  [{t['era']}] #{t['pos']}: {t['nom']} ({t['any']})")

# Obtenir portades via Spotify
print("\nObtenint portades Spotify...")
spotify_token = get_spotify_token()

clips_paths = []

for track in tracks:
    pos              = track['pos']
    nom              = track['nom']
    any_canco        = track.get('any', '')
    era              = track.get('era', 'THEN')
    cover_url        = track.get('cover_url')
    timestamp_manual = track.get('timestamp_manual')
    nom_manual       = track.get('nom_manual')
    durada           = DURADA_CLIP
    es_ultim         = (pos == len(tracks))
    color_era        = COLOR_THEN if era == 'THEN' else COLOR_NOW

    print(f"\nClip #{pos} [{era}]: {nom} ({any_canco})")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    audio_path = os.path.expanduser(f"~/videos/{pos:02d}.wav")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
    thumb_base = os.path.expanduser(f"~/videos/{pos:02d}_thumb")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    # Portada Spotify
    if spotify_token:
        cover_data = get_spotify_cover(nom, ARTISTA, spotify_token)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada Spotify OK")

    nom_query = nom.replace("'", "").replace('"', '').strip()
    if any(x in nom.lower() for x in ['remix', 'edit', 'mix', 'version']):
        query = f"{ARTISTA} {nom_query} official"
    else:
        query = f"{ARTISTA} {nom_query} {ARTISTA} official video"

    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        os.system(f'yt-dlp --write-thumbnail --skip-download --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{thumb_base}" "ytsearch1:{query}" -q 2>/dev/null')
        thumb_webp = thumb_base + ".webp"
        if not os.path.exists(thumb_path) and os.path.exists(thumb_webp):
            os.system(f'ffmpeg -i "{thumb_webp}" "{thumb_path}" -y -loglevel error')

    ret = os.system(f'yt-dlp -f "best[ext=mp4]/best" --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "ytsearch1:{query}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   No s'ha trobat videoclip — usant portada")
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
    titol1 = f"{ARTISTA.upper()} THEN vs NOW"
    nom = nom_manual if nom_manual else nom
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')
    nom_linia1, nom_linia2 = partir_nom(nom_net, max_chars=22)

    n_total = len(tracks)
    bar_progress = int(BAR_W * pos / n_total)

    txt = []
    txt.append(f"drawbox=x=0:y=0:w=1080:h=360:color=black@0.20:t=fill")
    txt.append(f"drawbox=x=0:y=1580:w=1080:h=340:color=black@0.18:t=fill")
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol1}':fontsize=72:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{era}':fontsize=280:fontcolor={color_era}@0.12:x=(w-text_w)/2:y=600")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{era}':fontsize=90:fontcolor={color_era}:borderw=2:bordercolor=black@0.8:shadowx=0:shadowy=3:x=(w-text_w)/2:y={Y_TITOL2}")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_linia1}':fontsize=58:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM1}")
    if nom_linia2:
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{nom_linia2}':fontsize=58:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x={X_INFO}:y={Y_NOM2}")
    if any_canco:
        txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{any_canco}':fontsize=44:fontcolor={color_era}:borderw=2:bordercolor=black@0.8:shadowx=0:shadowy=2:x={BAR_X}:y={Y_ANY}")
    txt.append(f"drawbox=x={BAR_X}:y={Y_BAR}:w={BAR_W}:h=5:color=white@0.15:t=fill")
    txt.append(f"drawbox=x={BAR_X}:y={Y_BAR}:w={bar_progress}:h=5:color={color_era}@0.9:t=fill")

    if es_ultim:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=50:fontcolor=white@0.82:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_OUTRO}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='Electronic Vibes Daily':fontsize=30:fontcolor=0x00BFFF@0.70:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y={Y_OUTRO2}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='Comment THEN or NOW':fontsize=44:fontcolor=white:borderw=2:bordercolor=black@0.7:x=(w-text_w)/2:y={Y_OUTRO3}:enable='gte(t,{t_aparicio})'")

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

clips_paths.sort(key=lambda x: x[0])
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
output_final = f"{OUTPUT}/thenvsnow_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" -c:v libx264 -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
