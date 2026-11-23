# torneig_preparar.py - prepara els clips del torneig UNA SOLA VEGADA.
# Per cada tema: troba el video de YouTube, detecta el moment del drop (o fa servir el timestamp manual), en baixa 14 s,
# els normalitza (1080x1920, -14 LUFS) i els puja al release 'torneig_clips'. Les rondes posteriors reutilitzen aquests clips
# sense tornar a YouTube. El resultat (moment detectat, titol del video trobat...) queda a torneig_clips.json.
import os, sys, json, re, subprocess, shutil, time, glob
import numpy as np
import librosa
from scipy.signal import find_peaks, butter, filtfilt
import requests

TRACKS = json.loads(os.environ['TRACKS'])
ESTIL = os.environ.get('ESTIL', 'energetic')
FORCAR = os.environ.get('FORCAR', '0') == '1'
REPO = os.environ.get('GITHUB_REPOSITORY', 'nilburgas-eng/onedayonevibe')
GH_TOKEN = os.environ.get('GITHUB_TOKEN', '')
FONT_LOCAL = os.environ.get('PREP_FONT_LOCAL', '')       # nomes proves: carpeta amb <id>.mp4 completes en lloc de YouTube
DURADA_CLIP = 14.0
WORK = os.path.expanduser('~/prep'); os.makedirs(WORK, exist_ok=True)
JSON_OUT = 'torneig_clips.json'
YTDLP_FORMAT = "bestvideo[height<=2160][vcodec!^=av01]+bestaudio[ext=m4a]/bestvideo[height<=2160][vcodec!^=av01]+bestaudio/bestvideo[height<=1440]+bestaudio/best[height<=1440]/best"
YT_COMU = "--cookies cookies.txt --js-runtime node --remote-components ejs:github --sleep-requests 1 --extractor-retries 3 --no-playlist"
SENYALS_BLOQUEIG = ("HTTP Error 429", "HTTP Error 403", "Sign in to confirm", "not a bot", "Failed to extract any player response")


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


def youtube_bloquejat(url_prova):
    """Si YouTube bloqueja el runner (cookies caducades o IP limitada) ho sabem abans de gastar 20 minuts."""
    if FONT_LOCAL: return False
    try:
        r = subprocess.run(['yt-dlp', '--simulate', '--skip-download', '--no-playlist', '--cookies', 'cookies.txt',
                            '--js-runtime', 'node', '--remote-components', 'ejs:github', url_prova], capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"   (comprovacio de YouTube no concloent: {e})"); return False
    if r.returncode == 0: return False
    return any(x in (r.stderr or "") for x in SENYALS_BLOQUEIG)


def sh(cmd, timeout=900):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def yt_info(font, tid):
    """(url_resolta, titol, durada) o None."""
    if FONT_LOCAL:
        p = os.path.join(FONT_LOCAL, f"{tid}.mp4")
        if not os.path.exists(p): return None
        d = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p], capture_output=True, text=True).stdout.strip())
        return p, f"(local) {tid}", d
    r = sh(f'yt-dlp --dump-json --no-download {YT_COMU} "{font}"', 120)
    if r.returncode != 0 or not r.stdout:
        print("   " + (r.stderr or '')[-300:]); return None
    info = json.loads(r.stdout.splitlines()[0])
    return info.get('webpage_url') or font, info.get('title', ''), float(info.get('duration') or 0)


def yt_audio(url, tid, out_wav):
    if FONT_LOCAL:
        return sh(f'ffmpeg -y -loglevel error -i "{url}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{out_wav}"').returncode == 0
    for f in glob.glob(f"{WORK}/{tid}_audio.*"): os.remove(f)
    r = sh(f'yt-dlp -f bestaudio {YT_COMU} -o "{WORK}/{tid}_audio.%(ext)s" "{url}" -q')
    fs = glob.glob(f"{WORK}/{tid}_audio.*")
    if r.returncode != 0 or not fs:
        print("   " + (r.stderr or '')[-300:]); return False
    ok = sh(f'ffmpeg -y -loglevel error -i "{fs[0]}" -vn -acodec pcm_s16le -ar 22050 -ac 1 "{out_wav}"').returncode == 0
    os.remove(fs[0]); return ok


def yt_tros(url, ini, fi, out_mp4):
    if os.path.exists(out_mp4): os.remove(out_mp4)
    if FONT_LOCAL:
        return sh(f'ffmpeg -y -loglevel error -ss {ini:.2f} -i "{url}" -t {fi - ini:.2f} -c copy "{out_mp4}"').returncode == 0
    # Alguns videos fallen amb el format/tall habitual (p. ex. "ffmpeg exited with code 146"):
    # es reintenta amb estrategies cada cop mes conservadores abans de donar-lo per perdut.
    F1080 = "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    intents = [
        (YTDLP_FORMAT, '--force-keyframes-at-cuts', None, 1200),
        (YTDLP_FORMAT, '', "tall sense forcar keyframes (pot sortir uns segons abans)", 900),
        (F1080, '', "versio 1080p compatible (menys resolucio)", 900),
        ("best[height<=720]/best", '', "versio 720p (poca resolucio)", 900),
    ]
    for fmt, extra, avis, tmo in intents:
        if os.path.exists(out_mp4): os.remove(out_mp4)
        try:
            r = sh(f'yt-dlp -f "{fmt}" --download-sections "*{ini:.2f}-{fi:.2f}" {extra} --merge-output-format mp4 {YT_COMU} -o "{out_mp4}" "{url}" -q', tmo)
            err = (r.stderr or '')[-300:]
        except subprocess.TimeoutExpired:
            err = "(temps esgotat)"
        if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 10000:
            if avis: print(f"   AVIS: ha funcionat amb {avis}")
            return True
        print("   " + err.strip() + "\n   -> es reintenta amb una altra estrategia")
    return False


def puja_clip(path, nom_asset):
    if not GH_TOKEN or os.environ.get('TORNEIG_NO_UPLOAD'):
        print("   (no es puja: sense GITHUB_TOKEN o mode prova)"); return True
    h = {"Authorization": f"token {GH_TOKEN}"}
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/torneig_clips", headers=h)
    if r.status_code == 200: rel = r.json()
    else:
        r = requests.post(f"https://api.github.com/repos/{REPO}/releases", headers=h, json={"tag_name": "torneig_clips", "name": "torneig_clips", "draft": False})
        if r.status_code not in (200, 201):
            print(f"   ERROR creant release: {r.status_code} {r.text}"); return False
        rel = r.json()
    for a in rel.get('assets', []):
        if a['name'] == nom_asset: requests.delete(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}", headers=h)
    up = rel['upload_url'].split('{')[0]
    with open(path, 'rb') as f:
        r2 = requests.post(f"{up}?name={nom_asset}", headers={**h, "Content-Type": "video/mp4"}, data=f)
    print(f"   Pujat {nom_asset}: {r2.status_code} ({os.path.getsize(path) / 1048576:.1f} MB)")
    return r2.status_code in (200, 201)


def desa(dades):
    with open(JSON_OUT, 'w', encoding='utf-8') as f: json.dump(dades, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    dades = json.load(open(JSON_OUT, encoding='utf-8')) if os.path.exists(JSON_OUT) else {}
    primer = next((t for t in TRACKS if t.get('yt_url')), TRACKS[0])
    url_prova = primer.get('yt_url') or f"ytsearch1:{primer['artista']} {primer['nom']} official video"
    if youtube_bloquejat(url_prova):
        print("\nERROR: YouTube esta bloquejant les baixades (error 429/403).")
        print("   Causa probable: cookies caducades o IP del servidor temporalment limitada.")
        print("   Que fer: 1) renova cookies.txt al Drive; 2) si ja son noves, espera unes hores i torna-ho a provar.")
        sys.exit(1)
    fets = []; fallats = []
    for n, t in enumerate(TRACKS):
        tid = t['id']; nom = t['nom']; artista = t['artista']; url_in = (t.get('yt_url') or '').strip()
        ini_man = t.get('inici')
        prev = dades.get(tid)
        print(f"\n[{n + 1}/{len(TRACKS)}] {nom} - {artista}")
        if (prev and prev.get('ok') and not FORCAR and prev.get('url_input', '') == url_in
                and (ini_man is None or abs(float(ini_man) - float(prev['inici'])) < 1)):
            print("   Ja preparat: es reutilitza"); fets.append(tid); continue
        if n: time.sleep(3)
        font = url_in or f"ytsearch1:{artista} {nom} official video"
        info = yt_info(font, tid)
        if not info:
            print("   ERROR: no s'ha trobat el video"); fallats.append(nom); dades[tid] = {"ok": False, "url_input": url_in, "error": "video no trobat"}; desa(dades); continue
        url, titol, dur = info
        print(f"   Video: {titol} ({int(dur // 60)}:{int(dur % 60):02d})")
        auto = ini_man is None
        if auto:
            wav = f"{WORK}/{tid}.wav"
            if yt_audio(url, tid, wav):
                inici = trobar_moment_impactant(wav, dur, ESTIL); os.remove(wav)
            else:
                print("   AVIS: no s'ha pogut baixar l'audio per detectar el drop (es fa servir 0:45)"); inici = 45.0
            print(f"   Drop detectat: {int(inici // 60)}:{int(inici % 60):02d}")
        else:
            inici = float(ini_man); print(f"   Timestamp manual: {int(inici // 60)}:{int(inici % 60):02d}")
        inici = max(0.0, min(inici, max(0.0, dur - DURADA_CLIP - 0.5)))
        raw = f"{WORK}/{tid}_raw.mp4"; out = f"{WORK}/clip_{tid}.mp4"
        if not yt_tros(url, inici, inici + DURADA_CLIP, raw):
            print("   ERROR: no s'ha pogut baixar el tros"); fallats.append(nom); dades[tid] = {"ok": False, "url_input": url_in, "error": "descarrega fallida"}; desa(dades); continue
        pr = json.loads(subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', raw], capture_output=True, text=True).stdout or '{}')
        res = next((f"{s.get('width')}x{s.get('height')}" for s in pr.get('streams', []) if s.get('codec_type') == 'video'), '?')
        print(f"   Resolucio baixada: {res}")
        r = sh(f'ffmpeg -y -loglevel error -i "{raw}" -t {DURADA_CLIP} -vf "scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" '
               f'-af "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -c:a aac -b:a 320k -ar 48000 -movflags +faststart "{out}"')
        os.remove(raw)
        if r.returncode != 0 or not os.path.exists(out):
            print("   ERROR convertint el clip:", (r.stderr or '')[-300:]); fallats.append(nom); continue
        if not puja_clip(out, f"clip_{tid}.mp4"):
            fallats.append(nom); continue
        os.remove(out)
        dades[tid] = {"ok": True, "inici": round(inici, 2), "auto": auto, "url_input": url_in, "url": url, "titol_yt": titol,
                      "yt_durada": round(dur), "resolucio": res, "actualitzat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        desa(dades); fets.append(tid)
    desa(dades)
    print(f"\nPreparats: {len(fets)} / {len(TRACKS)}")
    if fallats:
        print("Amb problemes (revisa el titol/enllac de YouTube i torna-ho a provar): " + ", ".join(fallats)); sys.exit(1)
