import os, json, re, subprocess, shutil
import requests

OUTPUT = os.path.expanduser("~/output")
FONTS  = os.path.expanduser("~/fonts")
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

SET_URL      = os.environ.get('SET_URL', '').strip()
DJ           = os.environ.get('DJ', '')
COMPTE       = "@onedayonevibe"
TOP_N        = 5
DURADA_CLIP  = 10
DURADA_OUTRO = 2.0
FADE_DURADA  = 0.3
PADDING      = 2.0   # marge de seguretat al baixar cada tram exacte

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"

LOGO_PATH    = "logo.png"
LOGO_W       = 90
LOGO_OPACITY = 0.85
LOGO_MARGIN  = 30
LOGO_ACTIU   = os.path.exists(LOGO_PATH)

PADDING_X = 100
Y_TITOL1  = 260
Y_TITOL2  = 340
Y_BASE    = 490
Y_SEP     = 78


def baixar_tram(url, inici, durada_tram, output_path):
    """Baixa nomes el tram [inici, inici+durada_tram] del video font, sense baixar-lo sencer."""
    fi = inici + durada_tram
    cmd = (
        f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" '
        f'--download-sections "*{inici:.2f}-{fi:.2f}" --force-keyframes-at-cuts '
        f'--merge-output-format mp4 --cookies cookies.txt --js-runtime node '
        f'--remote-components ejs:github -o "{output_path}" "{url}" -q'
    )
    ret = os.system(cmd)
    return ret == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000


if not SET_URL:
    print("ERROR: falta SET_URL")
    exit(1)

TRACKS_RAW = os.environ.get('TRACKS', '[]')
print("Carregant tracks rebuts...")
tracks = json.loads(TRACKS_RAW)

if len(tracks) < 2:
    print("ERROR: calen com a minim 2 temes")
    exit(1)

print(f"\nSet: {SET_URL}")
print(f"Tracks ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['numero']}: {t['nom']} @ {t['timestamp']}")

noms_nets = {}
for t in tracks:
    numero = int(t['numero'])
    nom_net = str(t['nom']).replace("'", "").replace('"', '').replace(':', '-').strip()
    noms_nets[numero] = nom_net

compte_text = COMPTE.replace("'", "").replace('"', '')
os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

clips_paths = []
tracks_ordenats = sorted(tracks, key=lambda t: -int(t['numero']))

for i, track in enumerate(tracks_ordenats):
    numero       = int(track['numero'])
    nom          = noms_nets[numero]
    timestamp    = float(track['timestamp'])
    durada_extra = float(track.get('durada_extra') or 0)
    durada_base  = DURADA_CLIP + durada_extra
    durada       = durada_base + DURADA_OUTRO if numero == 1 else durada_base
    posicio      = i + 1

    print(f"\nGenerant clip {posicio} (#{numero}): {nom} @ {int(timestamp//60):02d}:{int(timestamp%60):02d}")

    tram_path = os.path.expanduser(f"~/videos/tram_{numero:02d}.mp4")
    output_path = f"{OUTPUT}/clip_{numero:02d}.mp4"

    inici_baixada = max(0, timestamp - PADDING)
    durada_baixada = durada + 2 * PADDING
    ok = baixar_tram(SET_URL, inici_baixada, durada_baixada, tram_path)

    if not ok:
        print(f"   ERROR: no s'ha pogut baixar el tram per #{numero} - clip descartat")
        clips_paths.append((numero, output_path))
        continue

    offset_dins_tram = min(PADDING, timestamp)

    titol1 = "TOP 5 MOMENTS"
    titol2 = DJ.upper().replace("'", "").replace('"', '')

    filtres = []
    filtres.append(f"drawtext=fontfile='{FONT_BEBAS}':text='{titol1}':fontsize=98:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.35:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    filtres.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{titol2}':fontsize=44:fontcolor=0x00BFFF:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.25:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL2}")

    for n in range(5, 0, -1):
        pos_visual = 5 - n
        y_pos = Y_BASE + pos_visual * Y_SEP
        filtres.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{n}.':fontsize=76:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.30:shadowx=0:shadowy=2:x={PADDING_X}:y={y_pos}")

    for n in range(5, 0, -1):
        pos_visual = 5 - n
        y_pos = Y_BASE + pos_visual * Y_SEP + 12
        canco_net = noms_nets.get(n, '')
        posicio_aparicio = TOP_N - n + 1
        if posicio >= posicio_aparicio and canco_net:
            filtres.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{canco_net}':fontsize=42:fontcolor=white:borderw=1:bordercolor=black@0.8:shadowcolor=black@0.30:shadowx=0:shadowy=2:x={PADDING_X + 90}:y={y_pos}")

    if numero == 1:
        t_aparicio = durada_base - 0.3
        filtres.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=54:fontcolor=white@0.85:shadowcolor=black@0.25:shadowx=0:shadowy=2:x=(w-text_w)/2:y=(h/2)+180:enable='gte(t,{t_aparicio})'")
        filtres.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='Electronic Vibes Daily':fontsize=30:fontcolor=0x00BFFF@0.75:shadowcolor=black@0.20:shadowx=0:shadowy=1:x=(w-text_w)/2:y=(h/2)+248:enable='gte(t,{t_aparicio})'")

    vf = ",".join(filtres)
    fc = f'[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,setsar=1,colorchannelmixer=ra=0.85:ga=0.85:ba=0.85,{vf}[out]'
    inputs = f'-ss {offset_dins_tram:.2f} -i "{tram_path}"'
    if LOGO_ACTIU:
        fc += f";[1:v]scale={LOGO_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[logo];[out][logo]overlay=W-w-{LOGO_MARGIN}:{LOGO_MARGIN}[final]"
        inputs += f' -i "{LOGO_PATH}"'
        mapa_final = "[final]"
    else:
        mapa_final = "[out]"

    cmd = f'ffmpeg {inputs} -t {durada} -filter_complex "{fc}" -map "{mapa_final}" -map 0:a {VIDEO_OPTS} -c:a aac -b:a 192k "{output_path}" -y -loglevel error'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    mida = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    if mida > 1000:
        r_check = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", output_path], capture_output=True, text=True)
        info_check = json.loads(r_check.stdout) if r_check.stdout else {}
        durada_real = float(info_check.get('format', {}).get('duration', 0))
        if durada_real > 0.5:
            print(f"   OK clip generat ({mida//1024} KB, {durada_real:.1f}s)")
        else:
            print(f"   ERROR: clip #{numero} sense durada valida")
            print(f"   FFMPEG STDERR: {result.stderr[-1500:]}")
    else:
        print(f"   ERROR: clip #{numero} no generat correctament (mida={mida})")
        print(f"   FFMPEG STDERR: {result.stderr[-1500:]}")

    clips_paths.append((numero, output_path))

clips_paths.sort(key=lambda x: x[0], reverse=True)
clips_valids = []
durades = []
for numero, path in clips_paths:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
        info_dur = json.loads(r.stdout) if r.stdout else {}
        dur = float(info_dur.get('format', {}).get('duration', 0)) if 'format' in info_dur else 0
        if dur > 0.5:
            clips_valids.append(path)
            durades.append(dur)
        else:
            print(f"   Clip #{numero} descartat (durada invalida): {path}")
    else:
        print(f"   Clip #{numero} descartat: {path}")

if len(clips_valids) < 2:
    print("ERROR: no hi ha prou clips valids per muntar el video final")
    exit(1)

print(f"\nMuntant video final amb {len(clips_valids)} clips...")

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

filter_complex = ";".join(video_filters + audio_filters)
output_final = f"{OUTPUT}/top5_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
ret_final = os.system(cmd)
if ret_final != 0 or not os.path.exists(output_final) or os.path.getsize(output_final) < 10000:
    print(f"ERROR: muntatge final ha fallat (codi {ret_final})")
else:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", output_final], capture_output=True, text=True)
    durada_total = float(json.loads(r.stdout)['format']['duration'])
    print(f"Video final generat! Durada: {durada_total:.1f}s amb {n_clips} clips")
