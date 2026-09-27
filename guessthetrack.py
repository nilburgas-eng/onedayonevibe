import os, json, re, subprocess, base64, shutil, random
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

SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
FONS_URL          = os.environ.get('FONS_URL', '').strip()    # video generic de fons (nomes visual, com top10drops)
MARGE_FONS        = 15.0
PADDING_FONS      = 1.0
SPOTIFY_SECRET    = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
COMPTE            = "@onedayonevibe"
N_RONDES          = 8
DURADA_RONDA      = 4.5
REVEAL_ABANS_FI   = 1.5     # segons abans del final on es revela la resposta
DURADA_OUTRO      = 2.0
FADE_DURADA       = 0.3

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"

SPEED_FACTOR = 1.03

COLOR_ACCENT = "0x00BFFF"
COLOR_WHITE  = "white"

COVER_W  = 320
COVER_H  = 320
COVER_X  = 380
COVER_Y  = 640
BLUR_FORCA = "24:2"   # luma_radius:luma_power

Y_TITOL1   = 260
Y_TITOL2   = 330
Y_RONDA    = 1080
Y_COMMENT  = 1180
Y_RESULTAT1 = 1080
Y_RESULTAT2 = 1150
Y_OUTRO    = 1560
Y_OUTRO2   = 1618

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
STICKER_Y = 1300

def trobar_fitxer_per_prefix(prefix):
    """Busca un fitxer al directori actual que comenci per 'prefix', sigui quina sigui l'extensio."""
    for f in os.listdir('.'):
        if f.lower().startswith(prefix.lower()):
            return f
    return None

INTRO_AUDIO_PATH = trobar_fitxer_per_prefix("intro_audio.")


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
        print(f"   ERROR consultant durada del link general: {e}")
        return None

def baixar_tros_fons(url, inici, durada_tros, output_path):
    fi = inici + durada_tros
    cmd = (
        f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]/best[ext=mp4]/best" '
        f'--download-sections "*{inici:.2f}-{fi:.2f}" --force-keyframes-at-cuts '
        f'--merge-output-format mp4 --cookies cookies.txt --js-runtime node '
        f'--remote-components ejs:github -o "{output_path}" "{url}" -q'
    )
    ret = os.system(cmd)
    return ret == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000

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


TRACKS_RAW = os.environ.get('TRACKS', '')
print("Carregant tracks rebuts...")
tracks = json.loads(TRACKS_RAW)
for t in tracks:
    if t.get('timestamp_manual') not in (None, '', 0):
        t['timestamp_manual'] = float(t['timestamp_manual'])
    else:
        t['timestamp_manual'] = None

if len(tracks) < 2:
    print("ERROR: calen com a minim 2 rondes")
    exit(1)

print(f"\nRondes ({len(tracks)}):")
for t in tracks:
    print(f"  #{t['pos']}: {t['nom']} - {t['artista']}")

print("\nObtenint token de Spotify...")
spotify_token = get_spotify_token()
print("Token OK" if spotify_token else "Sense token Spotify")

max_pos = max(t['pos'] for t in tracks)
if STICKER_ACTIU:
    print(f"\nStickers Follow/Thanks actius, apareixeran a la primera ronda (#{max_pos})")

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
            durada_ronda_i = DURADA_RONDA + (DURADA_OUTRO if track['pos'] == 1 else 0)
            marge_bucket = max(0, bucket - durada_ronda_i)
            inici_bucket = usable_inici + i * bucket
            offset = inici_bucket + random.uniform(0, marge_bucket)
            offsets_fons[track['pos']] = max(0, min(offset, durada_fons_total - durada_ronda_i - 0.5))
    else:
        print(f"   AVIS: no s'ha pogut consultar la durada, es descarta el video de fons")
        FONS_URL = ''

clips_paths = []

if INTRO_AUDIO_PATH:
    print(f"\nAudio d'intro trobat: {INTRO_AUDIO_PATH} (es barrejara amb la primera ronda)")

for track in tracks:
    pos              = track['pos']
    nom              = track['nom']
    artista          = track.get('artista', '')
    yt_url           = track.get('yt_url')
    timestamp_manual = track.get('timestamp_manual')
    ronda_num        = track.get('ronda', pos)

    es_ultim  = (pos == 1)
    es_primer = (pos == max_pos)
    durada = DURADA_RONDA + (DURADA_OUTRO if es_ultim else 0)
    reveal_t = durada - REVEAL_ABANS_FI

    print(f"\nRonda {ronda_num} (#{pos}): {nom} - {artista}")

    video_path = os.path.expanduser(f"~/videos/{pos:02d}.mp4")
    thumb_path = os.path.expanduser(f"~/videos/{pos:02d}_thumb.jpg")
    os.makedirs(os.path.expanduser("~/videos"), exist_ok=True)

    # ---------- PORTADA (ordre fix: Spotify tema -> artista -> YouTube propi) ----------
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
            print(f"   Portada Spotify artista OK (fallback)")
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        cover_data = get_youtube_thumbnail(yt_url)
        if cover_data:
            with open(thumb_path, 'wb') as f:
                f.write(cover_data)
            print(f"   Portada YouTube OK (fallback)")
    if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 1000:
        print(f"   AVIS: cap portada trobada per aquest track")

    # ---------- CANCO ----------
    if yt_url:
        print(f"   URL manual: {yt_url}")
        ret = os.system(f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{yt_url}" --no-playlist -q')
    else:
        font_cerca = f"ytsearch1:{artista} {nom} official audio"
        print(f"   Cerca: {artista} {nom}")
        ret = os.system(f'yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{font_cerca}" --no-playlist -q')

    if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
        print(f"   ERROR: no s'ha pogut baixar l'audio - ronda descartada")
        continue

    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path], capture_output=True, text=True)
    info = json.loads(r.stdout)
    duracio_total = float(info['format']['duration'])

    if timestamp_manual is not None:
        inici = float(timestamp_manual)
        print(f"   Timestamp manual (el drop): {int(inici//60):02d}:{int(inici%60):02d}")
    else:
        inici = 30.0
        print(f"   AVIS: sense timestamp manual, usant 00:30 per defecte")
    inici = max(0, min(inici, duracio_total - durada - 0.5))

    usar_fons_visual = False
    fons_path = os.path.expanduser(f"~/videos/{pos:02d}_fons.mp4")
    if FONS_URL and pos in offsets_fons:
        offset_fons = offsets_fons[pos]
        inici_baixada = max(0, offset_fons - PADDING_FONS)
        durada_baixada = durada + 2 * PADDING_FONS
        print(f"   Video generic pel fons visual ({int(offset_fons//60):02d}:{int(offset_fons%60):02d})")
        ok_fons = baixar_tros_fons(FONS_URL, inici_baixada, durada_baixada, fons_path)
        if ok_fons:
            usar_fons_visual = True
        else:
            print(f"   AVIS: no s'ha pogut baixar el tram generic, s'usa el video propi")

    output_path = f"{OUTPUT}/clip_{pos:02d}.mp4"
    nom_net = nom.replace("'", "").replace('"', '').replace(':', '-')
    artista_net = artista.replace("'", "").replace('"', '').replace(':', '-')

    has_thumb = os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    txt = []
    txt.append(f"drawbox=x=0:y=0:w=1080:h=440:color=black@0.24:t=fill")
    txt.append(f"drawbox=x=0:y=1580:w=1080:h=340:color=black@0.18:t=fill")
    txt.append(f"drawtext=fontfile='{FONT_BEBAS}':text='GUESS THE TRACK':fontsize=70:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_TITOL1}")
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='ROUND {ronda_num}/{N_RONDES}':fontsize=42:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_TITOL2}")

    txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='COMMENT YOUR GUESS 👇':fontsize=38:fontcolor=white@0.85:borderw=2:bordercolor=black@0.7:x=(w-text_w)/2:y={Y_COMMENT}:enable='lt(t,{reveal_t})'")

    resultat1 = f"{nom_net}"
    resultat2 = f"{artista_net}"
    txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{resultat1}':fontsize=54:fontcolor=white:borderw=3:bordercolor=black@0.9:shadowx=0:shadowy=2:x=(w-text_w)/2:y={Y_RESULTAT1}:enable='gte(t,{reveal_t})'")
    txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{resultat2}':fontsize=42:fontcolor={COLOR_ACCENT}:borderw=2:bordercolor=black@0.8:x=(w-text_w)/2:y={Y_RESULTAT2}:enable='gte(t,{reveal_t})'")

    if es_ultim:
        compte_text = COMPTE.replace("'", "")
        t_aparicio = durada - DURADA_OUTRO + 0.3
        txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='{compte_text}':fontsize=50:fontcolor=white@0.82:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y={Y_OUTRO}:enable='gte(t,{t_aparicio})'")
        txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='Electronic Vibes Daily':fontsize=30:fontcolor={COLOR_ACCENT}@0.70:borderw=1:bordercolor=black@0.5:x=(w-text_w)/2:y={Y_OUTRO2}:enable='gte(t,{t_aparicio})'")

    txt_str = ",".join(txt)

    input_parts = [f'-ss {inici} -i "{video_path}"']
    audio_idx = 0
    visual_idx = 0
    seguent_idx = 1

    if usar_fons_visual:
        offset_dins_tros = min(PADDING_FONS, offsets_fons[pos])
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

    sticker_follow_idx = None
    sticker_thanks_idx = None
    if es_primer and STICKER_ACTIU:
        input_parts.append(f'-loop 1 -i "{STICKER_FOLLOW_PATH}"')
        sticker_follow_idx = seguent_idx
        seguent_idx += 1
        input_parts.append(f'-loop 1 -i "{STICKER_THANKS_PATH}"')
        sticker_thanks_idx = seguent_idx
        seguent_idx += 1

    intro_idx = None
    if es_primer and INTRO_AUDIO_PATH:
        input_parts.append(f'-i "{INTRO_AUDIO_PATH}"')
        intro_idx = seguent_idx
        seguent_idx += 1

    inputs = " ".join(input_parts)

    fc_parts = [f"[{visual_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2[bg]"]

    current = "bg"
    if has_thumb:
        fc_parts.append(
            f"[{thumb_idx}:v]scale={COVER_W}:{COVER_H}:force_original_aspect_ratio=decrease,"
            f"pad={COVER_W}:{COVER_H}:(ow-iw)/2:(oh-ih)/2:color=black@0.9,setsar=1,split=2[coversharp][covertoblur]"
        )
        fc_parts.append(f"[covertoblur]boxblur={BLUR_FORCA}[coverblur]")
        fc_parts.append(f"[{current}][coverblur]overlay={COVER_X}:{COVER_Y}:enable='lt(t,{reveal_t})'[withblur]")
        fc_parts.append(f"[withblur][coversharp]overlay={COVER_X}:{COVER_Y}:enable='gte(t,{reveal_t})'[withcover]")
        current = "withcover"

    fc_parts.append(f"[{current}]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored]")
    fc_parts.append(f"[colored]{txt_str},setpts=PTS/{SPEED_FACTOR}[txted]")

    if intro_idx is not None:
        fc_parts.append(f"[{audio_idx}:a]atempo={SPEED_FACTOR}[songa]")
        fc_parts.append(f"[songa][{intro_idx}:a]amix=inputs=2:duration=first:dropout_transition=2[aout]")
    else:
        fc_parts.append(f"[{audio_idx}:a]atempo={SPEED_FACTOR}[aout]")

    if es_primer and STICKER_ACTIU:
        fc_parts.append(
            f"[{sticker_follow_idx}:v]scale={STICKER_W}:-1,format=rgba,"
            f"fade=t=in:st=0.3:d=0.3:alpha=1,fade=t=out:st=1.4:d=0.3:alpha=1[stfollow]"
        )
        fc_parts.append(
            f"[{sticker_thanks_idx}:v]scale={STICKER_W}:-1,format=rgba,"
            f"fade=t=in:st=1.4:d=0.3:alpha=1,fade=t=out:st=2.5:d=0.3:alpha=1[stthanks]"
        )
        fc_parts.append(f"[txted][stfollow]overlay=(W-w)/2:{STICKER_Y}:enable='between(t,0.3,1.7)'[stk1]")
        fc_parts.append(f"[stk1][stthanks]overlay=(W-w)/2:{STICKER_Y}:enable='between(t,1.4,2.8)'[out]")
    else:
        fc_parts.append("[txted]copy[out]")

    if LOGO_ACTIU:
        fc_parts.append(f"[{logo_idx}:v]scale={LOGO_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[logo]")
        fc_parts.append(f"[out][logo]overlay=W-w-{LOGO_MARGIN}:{LOGO_MARGIN}[final]")
        mapa_final = "[final]"
    else:
        mapa_final = "[out]"

    fc = ";".join(fc_parts)
    cmd = f'ffmpeg {inputs} -t {durada} -filter_complex "{fc}" -map "{mapa_final}" -map "[aout]" {VIDEO_OPTS} -r 30 -c:a aac -b:a 192k -ar 44100 "{output_path}" -y -loglevel error'

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    mida = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    if mida > 1000:
        print(f"   OK ronda generada ({mida//1024} KB)")
    else:
        print(f"   ERROR: ronda #{pos} no generada correctament (mida={mida})")
        print(f"   FFMPEG STDERR: {result.stderr[-1500:]}")
    clips_paths.append((pos, output_path))

clips_paths.sort(key=lambda x: x[0], reverse=True)
clips_valids = []
for pos, path in clips_paths:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        clips_valids.append(path)
    else:
        print(f"   Ronda #{pos} descartada: {path}")

if len(clips_valids) < 2:
    print("ERROR: No hi ha prou rondes valides")
    exit(1)

print(f"\nMuntant video final amb {len(clips_valids)} rondes...")
durades = []
for path in clips_valids:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    durades.append(float(json.loads(r.stdout)['format']['duration']))

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
output_final = f"{OUTPUT}/guessthetrack_final.mp4"
cmd = f'ffmpeg {inputs_str} -filter_complex "{filter_complex}" -map "[vfinal]" -map "[afinal]" {VIDEO_OPTS} -c:a aac -b:a 192k "{output_final}" -y -loglevel error'
ret_final = os.system(cmd)
if ret_final != 0 or not os.path.exists(output_final) or os.path.getsize(output_final) < 10000:
    print(f"ERROR: muntatge final ha fallat (codi {ret_final})")
else:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", output_final], capture_output=True, text=True)
    durada_total = float(json.loads(r.stdout)['format']['duration'])
    print(f"Video final generat! Durada: {durada_total:.1f}s amb {n_clips} rondes")
