import os, json, re, glob, shutil, subprocess, time, requests
import librosa, numpy as np
from scipy.signal import find_peaks, butter, filtfilt
from datetime import datetime
import anthropic

INPUT  = os.path.expanduser("~/input")
OUTPUT = os.path.expanduser("~/output")
FONTS  = os.path.expanduser("~/fonts")
os.makedirs(INPUT, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)
os.makedirs(FONTS, exist_ok=True)

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

ANTHROPIC_KEY    = os.environ['ANTHROPIC_KEY']
TITOL_LINIA1     = "Top 5 Moments"
TITOL_LINIA2     = os.environ['DJ']
COMPTE           = "@onedayonevibe"
FINESTRA_SEGONS  = 30
TOP_N            = 5
DURADA_CLIP      = 10
DURADA_OUTRO     = 2.0
FADE_DURADA      = 0.3
VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"
PADDING_X        = 100
Y_TITOL1         = 260
Y_TITOL2         = 340
Y_BASE           = 490
Y_SEP            = 78

ts_raw = json.loads(os.environ.get('TIMESTAMPS_MANUALS', '{}'))
TIMESTAMPS_MANUALS = {int(k): v for k, v in ts_raw.items()}

noms_raw = json.loads(os.environ.get('NOMS_MANUALS', '{}'))
NOMS_MANUALS = {int(k): v for k, v in noms_raw.items()}

fi_raw = json.loads(os.environ.get('FORCAR_INICI', '{}'))
FORCAR_INICI = {int(k): v for k, v in fi_raw.items()}

dur_raw = json.loads(os.environ.get('DURADES_MANUALS', '{}'))
DURADES_MANUALS = {int(k): int(v) for k, v in dur_raw.items()}

AJUSTOS_CLIPS = {}

result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", f"{INPUT}/set.mp4"], capture_output=True, text=True)
info_video = json.loads(result.stdout)
DURADA_VIDEO = float(info_video['format']['duration'])
print(f"Durada: {int(DURADA_VIDEO//60):02d}:{int(DURADA_VIDEO%60):02d}")

subprocess.run(["ffmpeg", "-i", f"{INPUT}/set.mp4", "-vn", "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1", f"{INPUT}/audio.wav", "-y", "-loglevel", "error"])

comment_files = glob.glob(f"{INPUT}/*.json")
comments_data = None
for f in comment_files:
    with open(f, 'r', encoding='utf-8') as file:
        data = json.load(file)
        if 'comments' in data:
            comments_data = data['comments']
            break
print(f"{len(comments_data)} comentaris carregats")

audio_complet, sr_audio = librosa.load(f"{INPUT}/audio.wav", sr=22050, mono=True)
hop_length = 512
rms_audio = librosa.feature.rms(y=audio_complet, frame_length=2048, hop_length=hop_length)[0]
times_audio = librosa.frames_to_time(np.arange(len(rms_audio)), sr=sr_audio, hop_length=hop_length)
rms_smooth_audio = np.convolve(rms_audio, np.ones(200)/200, mode='same')
peaks_audio, _ = find_peaks(rms_smooth_audio, distance=sr_audio//hop_length*60, prominence=0.002)
peak_energies_audio = [(times_audio[p], rms_smooth_audio[p]) for p in peaks_audio]
peak_energies_audio.sort(key=lambda x: x[1], reverse=True)

def es_comentari_tracklist(text):
    if 'TRACKLIST' in text.upper() or 'tracklist' in text.lower():
        return True
    if re.search(r'^\d{1,2}:\d{2}\s*/', text, re.MULTILINE):
        return True
    lines = text.split('\n')
    count = 0
    for line in lines:
        if re.search(r'^\d{1,2}:\d{2}\s+\w', line.strip()):
            count += 1
        else:
            count = 0
        if count >= 4:
            return True
    return False

def extreure_timestamps_comentaris(comments):
    timestamps_raw = []
    for comment in comments:
        text = comment.get('text', '')
        likes = comment.get('like_count', 0)
        if es_comentari_tracklist(text):
            continue
        matches = re.findall(r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b', text)
        for match in matches:
            if match[2]:
                segons = int(match[0])*3600 + int(match[1])*60 + int(match[2])
            else:
                segons = int(match[0])*60 + int(match[1])
            if segons > 30 and segons < DURADA_VIDEO - 20:
                timestamps_raw.append({'segons': segons, 'likes': likes + 1})
    return timestamps_raw

def agrupar_timestamps(timestamps_raw, finestra=30):
    if not timestamps_raw:
        return []
    timestamps_raw.sort(key=lambda x: x['segons'])
    grups = []
    grup_actual = [timestamps_raw[0]]
    for ts in timestamps_raw[1:]:
        if ts['segons'] - grup_actual[-1]['segons'] <= finestra:
            grup_actual.append(ts)
        else:
            grups.append(grup_actual)
            grup_actual = [ts]
    grups.append(grup_actual)
    moments = []
    for grup in grups:
        mencions = len(grup)
        likes_total = sum(ts['likes'] for ts in grup)
        timestamp_min = int(min([ts['segons'] for ts in grup]))
        score = mencions * 2 + likes_total
        moments.append({
            'segons': timestamp_min,
            'mencions': mencions,
            'likes': likes_total,
            'score': score
        })
    moments.sort(key=lambda x: x['score'], reverse=True)
    return moments

def filtrar_moments_musicals(moments, comments_data, anthropic_key):
    client = anthropic.Anthropic(api_key=anthropic_key)
    moments_filtrats = []
    for moment in moments[:15]:
        t = moment['segons']
        mins = int(t//60)
        segs = int(t%60)
        timestamp_str = f"{mins}:{segs:02d}"
        comentaris_moment = []
        for comment in comments_data:
            text = comment.get('text', '')
            if timestamp_str in text or f"{mins}:{segs}" in text:
                comentaris_moment.append(text[:200])
        if not comentaris_moment:
            moment['avanc'] = 0
            moments_filtrats.append(moment)
            continue
        mostra = "\n".join(comentaris_moment[:10])
        try:
            missatge = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=100,
                messages=[{"role": "user", "content": "Analyze these comments about timestamp " + timestamp_str + " in an EDM DJ set.\n\nComments:\n" + mostra + "\n\nAnswer TWO things:\n1. Is this a MUSICAL moment or OTHER?\n2. Does the timestamp point to: BUILD, DROP, or UNKNOWN?\n\nReply ONLY:\nMUSICAL|BUILD\nor\nMUSICAL|DROP\nor\nMUSICAL|UNKNOWN\nor\nOTHER|UNKNOWN"}]
            )
            resposta = missatge.content[0].text.strip().upper()
            time.sleep(2)
        except Exception as e:
            print(f"Error API: {timestamp_str}")
            resposta = "MUSICAL|UNKNOWN"
        parts = resposta.split('|')
        es_musical = parts[0].strip() == 'MUSICAL'
        if es_musical:
            moment['avanc'] = 0
            moments_filtrats.append(moment)
            print(f"OK: {timestamp_str}")
        else:
            print(f"Descartat: {timestamp_str}")
    return moments_filtrats

def obtenir_moments_audio(n_necessaris, moments_existents, cancons_vistes, tracklist):
    moments_audio = []
    for t, energia in peak_energies_audio:
        if len(moments_audio) >= n_necessaris:
            break
        if t >= DURADA_VIDEO - 20:
            continue
        massa_proper = any(abs(t - m['segons']) < 60 for m in moments_existents + moments_audio)
        if massa_proper:
            continue
        canco = trobar_canco(int(t), tracklist)
        if canco not in cancons_vistes or canco == "ID?":
            if canco != "ID?":
                cancons_vistes.add(canco)
            moments_audio.append({
                'segons': int(t), 'mencions': 0, 'likes': 0, 'score': 0,
                'track': canco, 'avanc': 0
            })
    return moments_audio

def obtenir_tracklist(comments_data):
    millor_comment = None
    millor_count = 0
    for comment in comments_data:
        text = comment.get('text', '')
        if not es_comentari_tracklist(text):
            continue
        timestamps = re.findall(r'\b(\d{1,2}):(\d{2})\b', text)
        if not timestamps:
            continue
        last_ts = max(int(t[0])*60 + int(t[1]) for t in timestamps)
        count = len(timestamps)
        if last_ts >= 2700 and count > millor_count:
            millor_count = count
            millor_comment = comment
    if not millor_comment:
        for comment in comments_data:
            text = comment.get('text', '')
            if not es_comentari_tracklist(text):
                continue
            count = len(re.findall(r'\b\d{1,2}:\d{2}\b', text))
            if count > millor_count:
                millor_count = count
                millor_comment = comment
    if not millor_comment:
        return {}
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = (
        "Extract the tracklist from this DJ set comment. "
        "A line starting with MM:SS followed by artist/song is a tracklist entry. "
        "Lines starting with w/ are transitions, skip them. "
        "Skip acapellas, intros and unknown tracks. "
        "Return ONLY lines in this exact format: MM:SS Song Name. "
        "One song per line. No explanations.\n\n"
        "COMMENT:\n" + millor_comment['text'][:3000]
    )
    try:
        missatge = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        resposta = missatge.content[0].text.strip()
        tracklist = {}
        for line in resposta.split('\n'):
            m = re.search(r'^(\d{1,2}):(\d{2})\s+(.+)$', line.strip())
            if m:
                segons = int(m.group(1))*60 + int(m.group(2))
                nom = m.group(3).strip()
                if nom and len(nom) > 3:
                    tracklist[segons] = nom
        print(f"{len(tracklist)} cançons identificades")
        return tracklist
    except Exception as e:
        print(f"Error tracklist: {e}")
        return {}

def trobar_canco(timestamp_clip, tracklist, marge=5, max_distancia=180):
    if not tracklist:
        return "ID?"
    tracklist_ordenada = sorted(tracklist.items())
    canco_activa = None
    ts_activa = None
    for ts, nom in tracklist_ordenada:
        if ts <= timestamp_clip + marge:
            canco_activa = nom
            ts_activa = ts
        else:
            break
    if canco_activa and ts_activa:
        if timestamp_clip - ts_activa > max_distancia:
            return "ID?"
    return canco_activa if canco_activa else "ID?"

def netejar_nom_canco(nom, max_chars=28):
    nom = re.sub(r'w/\..*$', '', nom).strip()
    if len(nom) <= max_chars:
        return nom
    if ' - ' in nom:
        parts = nom.split(' - ')
        titol = parts[-1].strip()
        if len(titol) <= max_chars:
            return titol
    return nom[:max_chars].strip()

def netejar_nom_canco_ia(nom, anthropic_key):
    if nom == "ID?":
        return "ID?"
    client = anthropic.Anthropic(api_key=anthropic_key)
    prompt = (
        "You are a music metadata expert for EDM short videos in VERTICAL format (1080x1920). "
        "Reconstruct this track title to display cleanly on screen. "
        "CRITICAL: The maximum title length is 28 characters. If longer, shorten it. "
        "Rules: Remove Official Video/Visualizer/Lyrics/HD/Extended Mix/Original Mix. "
        "NEVER cut words mid-word. "
        "If mashup use: TITLE 1 vs TITLE 2. "
        "If remix use: TITLE (REMIXER). "
        "Keep only main artist. "
        "Use only ASCII characters. "
        "Return ONLY the final title in one single line. No explanations. No reanalysis.\n\n"
        "TRACK: " + nom
    )
    try:
        missatge = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )
        resultat = missatge.content[0].text.strip()
        resultat = resultat.split('\n')[0].strip()
        resultat = resultat.encode('ascii', 'ignore').decode('ascii')
        resultat = resultat.replace("'", "").replace('"', '').replace(':', '-').strip()
        if not resultat:
            return netejar_nom_canco(nom)
        return resultat
    except Exception as e:
        return netejar_nom_canco(nom)

def trobar_inici_optim(audio, sr, timestamp_ref, durada_clip, avanc=0):
    inici_cerca = max(0, timestamp_ref)
    fi_cerca = min(len(audio)/sr, timestamp_ref + 150)
    inici_sample = int(inici_cerca * sr)
    fi_sample = int(fi_cerca * sr)
    fragment = audio[inici_sample:fi_sample]
    if len(fragment) < sr * 2:
        return inici_cerca, timestamp_ref
    hop_length = 512
    frame_length = 2048
    rms = librosa.feature.rms(y=fragment, frame_length=frame_length, hop_length=hop_length)[0]
    times_rel = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    rms_smooth = np.convolve(rms, np.ones(10)/10, mode='same')
    nyq = sr / 2
    b_low, a_low = butter(4, 100/nyq, btype='low')
    fragment_sub = filtfilt(b_low, a_low, fragment)
    rms_sub = librosa.feature.rms(y=fragment_sub, frame_length=frame_length, hop_length=hop_length)[0]
    rms_sub_smooth = np.convolve(rms_sub, np.ones(10)/10, mode='same')
    b_mid, a_mid = butter(4, [300/nyq, 3000/nyq], btype='band')
    fragment_mid = filtfilt(b_mid, a_mid, fragment)
    rms_mid = librosa.feature.rms(y=fragment_mid, frame_length=frame_length, hop_length=hop_length)[0]
    rms_mid_smooth = np.convolve(rms_mid, np.ones(10)/10, mode='same')
    onset_env = librosa.onset.onset_strength(y=fragment, sr=sr, hop_length=hop_length)
    onset_smooth = np.convolve(onset_env, np.ones(10)/10, mode='same')
    llindar = np.max(rms_smooth) * 0.65
    candidats, _ = find_peaks(rms_smooth, height=llindar, distance=int(sr/hop_length*10))
    if len(candidats) == 0:
        candidats = [np.argmax(rms_smooth)]
    frames_validacio = int(5 * sr / hop_length)
    millor_candidat = None
    millor_score = -999
    for idx in candidats:
        idx_despres_fi = min(len(rms_smooth), idx + frames_validacio)
        segment_sub_despres = rms_sub_smooth[idx:idx_despres_fi]
        segment_mid_despres = rms_mid_smooth[idx:idx_despres_fi]
        segment_onset_despres = onset_smooth[idx:idx_despres_fi]
        if len(segment_sub_despres) < 3:
            continue
        score = 0
        sub_despres = np.mean(segment_sub_despres)
        sub_max = np.max(rms_sub_smooth) if np.max(rms_sub_smooth) > 0 else 1
        ratio_sub = sub_despres / sub_max
        if ratio_sub > 0.5: score += 3
        elif ratio_sub > 0.3: score += 1
        if len(segment_onset_despres) > 3:
            estabilitat = 1 / (np.std(segment_onset_despres) + 0.001)
            if estabilitat > 50: score += 2
            elif estabilitat > 20: score += 1
        if len(segment_mid_despres) > 0 and sub_despres > 0:
            ratio_speech = np.mean(segment_mid_despres) / (sub_despres + 0.001)
            if ratio_speech > 3.0: score -= 3
        if rms_smooth[idx] > np.mean(rms_smooth) * 1.2: score += 1
        if score > millor_score:
            millor_score = score
            millor_candidat = idx
    if millor_candidat is None:
        millor_candidat = np.argmax(rms_smooth)
    drop_time_abs = inici_cerca + times_rel[min(millor_candidat, len(times_rel)-1)]
    inici_final = max(0, drop_time_abs - 3)
    print(f"Ref: {int(timestamp_ref//60):02d}:{int(timestamp_ref%60):02d} | Drop: {int(drop_time_abs//60):02d}:{int(drop_time_abs%60):02d} | Inici: {int(inici_final//60):02d}:{int(inici_final%60):02d}")
    return inici_final, drop_time_abs

print("Analitzant comentaris...")
timestamps_raw = extreure_timestamps_comentaris(comments_data)
moments_comentaris = agrupar_timestamps(timestamps_raw, FINESTRA_SEGONS)
print(f"{len(moments_comentaris)} moments únics")

print("Filtrant moments...")
moments_filtrats = filtrar_moments_musicals(moments_comentaris, comments_data, ANTHROPIC_KEY)

print("Parsejant tracklist...")
tracklist = obtenir_tracklist(comments_data)

top_moments_nets = []
cancons_vistes = set()
for moment in moments_filtrats:
    if len(top_moments_nets) >= TOP_N:
        break
    canco = trobar_canco(moment['segons'], tracklist)
    if canco not in cancons_vistes or canco == "ID?":
        if canco != "ID?":
            cancons_vistes.add(canco)
        moment['track'] = canco
        top_moments_nets.append(moment)

if len(top_moments_nets) < TOP_N:
    n_falten = TOP_N - len(top_moments_nets)
    moments_audio = obtenir_moments_audio(n_falten, top_moments_nets, cancons_vistes, tracklist)
    top_moments_nets.extend(moments_audio)

top_moments_ordenats = sorted(top_moments_nets[:TOP_N], key=lambda x: x['score'])

clips_info = []
for i, moment in enumerate(top_moments_ordenats):
    posicio = i + 1
    numero_llista = TOP_N - i
    segons = TIMESTAMPS_MANUALS.get(numero_llista, moment['segons'])
    durada_extra = DURADES_MANUALS.get(numero_llista, 0)
    durada_base = DURADA_CLIP + durada_extra
    durada = durada_base + DURADA_OUTRO if numero_llista == 1 else durada_base
    clips_info.append({
        'posicio': posicio, 'numero': numero_llista, 'segons': segons,
        'track': moment['track'], 'avanc': moment.get('avanc', 0),
        'drop_time': segons, 'durada': durada, 'durada_base': durada_base
    })

print("Detectant drops...")
for clip in clips_info:
    _, drop_time = trobar_inici_optim(audio_complet, sr_audio, clip['segons'], clip['durada'], clip['avanc'])
    clip['drop_time'] = drop_time

cancons_assignades = set()
for clip in sorted(clips_info, key=lambda x: x['numero'], reverse=True):
    canco = trobar_canco(int(clip['drop_time']), tracklist)
    if canco != "ID?" and canco not in cancons_assignades:
        clip['track'] = canco
        cancons_assignades.add(canco)
    elif canco in cancons_assignades:
        clip['track'] = "ID?"
    else:
        clip['track'] = "ID?"

print("Simplificant noms...")
noms_nets = {}
for clip in clips_info:
    nom_net = netejar_nom_canco_ia(clip['track'], ANTHROPIC_KEY)
    noms_nets[clip['numero']] = nom_net
    time.sleep(1)

for numero, nom_manual in NOMS_MANUALS.items():
    noms_nets[numero] = nom_manual

print("Noms finals:")
for n in range(5, 0, -1):
    print(f"  #{n}: {noms_nets.get(n, 'ID?')}")

compte_text = COMPTE.replace("'", "").replace('"', '')
clips_paths = []

for clip in clips_info:
    posicio = clip['posicio']
    numero  = clip['numero']
    t       = clip['segons']
    durada  = clip['durada']
    durada_base = clip['durada_base']
    avanc   = clip['avanc']

    print(f"Generant clip {posicio} (#{numero})...")
    inici, _ = trobar_inici_optim(audio_complet, sr_audio, t, durada, avanc)

    if FORCAR_INICI.get(numero, False):
        inici = t

    output_path = f"{OUTPUT}/clip_{posicio:02d}.mp4"
    titol1 = TITOL_LINIA1.upper().replace("'", "").replace('"', '')
    titol2 = TITOL_LINIA2.upper().replace("'", "").replace('"', '')

    filtres = []
    filtres.append("drawtext=fontfile='" + FONT_BEBAS + "':text='" + titol1 + "':fontsize=98:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.35:shadowx=0:shadowy=2:x=(w-text_w)/2:y=" + str(Y_TITOL1))
    filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + titol2 + "':fontsize=44:fontcolor=0x00BFFF:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.25:shadowx=0:shadowy=2:x=(w-text_w)/2:y=" + str(Y_TITOL2))

    for n in range(5, 0, -1):
        pos_visual = 5 - n
        y_pos = Y_BASE + pos_visual * Y_SEP
        filtres.append("drawtext=fontfile='" + FONT_EXTRABOLD + "':text='" + str(n) + ".':fontsize=76:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.30:shadowx=0:shadowy=2:x=" + str(PADDING_X) + ":y=" + str(y_pos))

    for n in range(5, 0, -1):
        pos_visual = 5 - n
        y_pos = Y_BASE + pos_visual * Y_SEP + 12
        canco_net = noms_nets.get(n, '').replace("'", "").replace('"', '').replace(':', '-').strip()
        posicio_aparicio = TOP_N - n + 1
        if posicio >= posicio_aparicio and canco_net:
            filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + canco_net + "':fontsize=42:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.30:shadowx=0:shadowy=2:x=" + str(PADDING_X + 90) + ":y=" + str(y_pos))

    if numero == 1:
        t_aparicio = durada_base - 0.3
        filtres.append("drawtext=fontfile='" + FONT_SEMIBOLD + "':text='" + compte_text + "':fontsize=54:fontcolor=white@0.85:shadowcolor=black@0.25:shadowx=0:shadowy=2:x=(w-text_w)/2:y=(h/2)+180:enable='gte(t," + str(t_aparicio) + ")'")
        filtres.append("drawtext=fontfile='" + FONT_MEDIUM + "':text='Electronic Vibes Daily':fontsize=30:fontcolor=0x00BFFF@0.75:shadowcolor=black@0.20:shadowx=0:shadowy=1:x=(w-text_w)/2:y=(h/2)+248:enable='gte(t," + str(t_aparicio) + ")'")

    vf = ",".join(filtres)
    cmd = f'ffmpeg -ss {inici} -i "{INPUT}/set.mp4" -t {durada} -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,setsar=1,colorchannelmixer=ra=0.85:ga=0.85:ba=0.85,{vf}" {VIDEO_OPTS} -c:a aac -b:a 192k "{output_path}" -y -loglevel error'
    os.system(cmd)
    clips_paths.append(output_path)
    print(f"Clip {posicio} generat")

print("Muntant video final...")
durades = []
for path in clips_paths:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    d = float(json.loads(r.stdout)['format']['duration'])
    durades.append(d)

n_clips = len(clips_paths)
inputs_str = " ".join([f"-i '{p}'" for p in clips_paths])
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
output_final = f"{OUTPUT}/top5_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
os.system(cmd)
print("Video final generat!")
