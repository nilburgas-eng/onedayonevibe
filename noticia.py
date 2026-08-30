import os, json, re, subprocess, shutil
from datetime import date
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

TIPUS            = os.environ.get('TIPUS', 'tema')          # 'artista' o 'tema'
NOM              = os.environ.get('NOM', '')
ARTISTA          = os.environ.get('ARTISTA', '')
DATA_STR         = os.environ.get('DATA', '')                # YYYY-MM-DD
YT_URL           = os.environ.get('YT_URL', '')
VIDEO_MANUAL     = os.environ.get('VIDEO_MANUAL', '')
TIMESTAMP_MANUAL = os.environ.get('TIMESTAMP_MANUAL', '')
DURADA           = float(os.environ.get('DURADA', '10'))
COMPTE           = "@onedayonevibe"

VIDEO_OPTS = "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p"

COLOR_ACCENT = "0x00BFFF"

LOGO_PATH    = "logo.png"
LOGO_W       = 190
LOGO_OPACITY = 0.95
LOGO_ACTIU   = os.path.exists(LOGO_PATH)

BOX_X      = 60
BOX_W      = 860
BOX_Y      = 1380
BARRA_W    = 10

AMPLE_MAX_LINIA = BOX_W - 100
MIDES_LINIA3    = [58, 52, 46, 40, 34]

if not NOM or not DATA_STR:
    print("ERROR: falten NOM o DATA")
    exit(1)

any_d, mes_d, dia_d = map(int, DATA_STR.split('-'))
data_obj = date(any_d, mes_d, dia_d)
avui = date.today()
anys = avui.year - data_obj.year - ((avui.month, avui.day) < (data_obj.month, data_obj.day))

verb = "WAS BORN" if TIPUS == 'artista' else "WAS RELEASED"
mostrar_artista = (TIPUS == 'tema' and ARTISTA)

print(f"Tipus: {TIPUS} | Nom: {NOM} | Data: {DATA_STR} | Anys: {anys}")

def amplada_text(text, font_path, mida):
    try:
        font = ImageFont.truetype(font_path, mida)
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * mida * 0.55

def ajustar_text(text, font_path, ample_max, mides):
    text = text.strip()
    for mida in mides:
        if amplada_text(text, font_path, mida) <= ample_max:
            return mida
    return mides[-1]

video_path = os.path.expanduser("~/video.mp4")
output_final = f"{OUTPUT}/noticia_final.mp4"

if VIDEO_MANUAL:
    print(f"Video manual: {VIDEO_MANUAL}")
    ret = 1
    if VIDEO_MANUAL.startswith('http'):
        try:
            r = requests.get(VIDEO_MANUAL, timeout=180, stream=True)
            if r.status_code == 200:
                with open(video_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                if os.path.getsize(video_path) > 10000:
                    ret = 0
        except Exception as e:
            print(f"   ERROR descarregant video manual: {e}")
    elif os.path.exists(VIDEO_MANUAL) and os.path.getsize(VIDEO_MANUAL) > 10000:
        shutil.copy(VIDEO_MANUAL, video_path)
        ret = 0
elif YT_URL:
    print(f"URL YouTube: {YT_URL}")
    ret = os.system(f'yt-dlp -f "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best" --merge-output-format mp4 --cookies cookies.txt --js-runtime node --remote-components ejs:github -o "{video_path}" "{YT_URL}" --no-playlist -q')
else:
    print("ERROR: cal YT_URL o VIDEO_MANUAL")
    exit(1)

if ret != 0 or not os.path.exists(video_path) or os.path.getsize(video_path) < 10000:
    print("ERROR: no s'ha pogut obtenir el video de fons")
    exit(1)

inici = float(TIMESTAMP_MANUAL) if TIMESTAMP_MANUAL not in ('', None) else 0.0

nom_net = NOM.replace("'", "").replace('"', '')
artista_net = ARTISTA.replace("'", "").replace('"', '')

mida_linia3 = ajustar_text(f"{nom_net} {verb}", FONT_EXTRABOLD, AMPLE_MAX_LINIA, MIDES_LINIA3)

box_h = 260 if mostrar_artista else 210

txt = []
txt.append(f"drawbox=x={BOX_X}:y={BOX_Y}:w={BOX_W}:h={box_h}:color=black@0.78:t=fill")
txt.append(f"drawbox=x={BOX_X}:y={BOX_Y}:w={BARRA_W}:h={box_h}:color={COLOR_ACCENT}:t=fill")

tx = BOX_X + BARRA_W + 30
txt.append(f"drawtext=fontfile='{FONT_SEMIBOLD}':text='ON THIS DAY':fontsize=34:fontcolor=white@0.85:borderw=1:bordercolor=black@0.5:x={tx}:y={BOX_Y+30}")
txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{anys} YEARS AGO':fontsize=64:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x={tx}:y={BOX_Y+75}")
txt.append(f"drawtext=fontfile='{FONT_EXTRABOLD}':text='{nom_net} {verb}':fontsize={mida_linia3}:fontcolor=white:borderw=2:bordercolor=black@0.7:shadowx=0:shadowy=2:x={tx}:y={BOX_Y+150}")
if mostrar_artista:
    txt.append(f"drawtext=fontfile='{FONT_MEDIUM}':text='{artista_net}':fontsize=32:fontcolor=white@0.75:borderw=1:bordercolor=black@0.5:x={tx}:y={BOX_Y+215}")

txt_str = ",".join(txt)

fc = (
    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920:(iw-1080)/2:(ih-1920)/2[bg];"
    "[bg]fps=30,colorchannelmixer=ra=0.90:ga=0.90:ba=0.90[colored];"
    "[colored]{txt}[out]"
).format(txt=txt_str)

inputs = f'-ss {inici} -i "{video_path}"'
if LOGO_ACTIU:
    fc += f";[1:v]scale={LOGO_W}:-1,format=rgba,colorchannelmixer=aa={LOGO_OPACITY}[logo];[out][logo]overlay=(W-w)/2:150[final]"
    inputs += f' -i "{LOGO_PATH}"'
    mapa_final = "[final]"
else:
    mapa_final = "[out]"

cmd = f'ffmpeg {inputs} -t {DURADA} -filter_complex "{fc}" -map "{mapa_final}" -map 0:a {VIDEO_OPTS} -r 30 -c:a aac -b:a 192k -ar 44100 "{output_final}" -y -loglevel error'
os.system(cmd)

if os.path.exists(output_final) and os.path.getsize(output_final) > 10000:
    print("Video final generat!")
else:
    print("ERROR: el video final no s'ha generat correctament")
    exit(1)
