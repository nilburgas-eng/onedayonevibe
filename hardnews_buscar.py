import os, json, re, html as htmllib
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import requests
from readability import Document
import anthropic

# Entrada: URLS (un enllac per linia). Sortida: hardnews_data.json amb, per cada notícia,
# titular + resum en angles (IA), font i foto principal de l'article (og:image).

URLS_RAW      = os.environ.get('URLS', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')
MAX_NOTICIES  = 10
MODEL         = "claude-sonnet-4-6"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8,ca;q=0.7",
}


def meta(pagina, *claus):
    """Valor de la primera <meta property|name=clau content=...> que trobi."""
    for clau in claus:
        c = re.escape(clau)
        m = re.search(r'<meta[^>]+(?:property|name)=["\']' + c + r'["\'][^>]*?content=["\']([^"\']+)["\']', pagina, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*?(?:property|name)=["\']' + c + r'["\']', pagina, re.I)
        if m:
            return htmllib.unescape(m.group(1)).strip()
    return ''


def nom_font(url, pagina):
    nom = meta(pagina, 'og:site_name')
    if nom:
        return nom
    host = urlparse(url).netloc.lower()
    host = re.sub(r'^(www|m|amp)\.', '', host)
    base = host.split('.')[0] if host else ''
    return base.replace('-', ' ').title() if base else ''


def extreure(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    pagina = r.text
    doc = Document(pagina)
    titol = doc.title()
    text = re.sub(r'<[^>]+>', ' ', doc.summary())
    text = htmllib.unescape(re.sub(r'\s+', ' ', text)).strip()
    imatge = meta(pagina, 'og:image:secure_url', 'og:image', 'twitter:image', 'twitter:image:src')
    if imatge:
        imatge = urljoin(r.url, imatge)
    return {
        'titol': titol,
        'text': text,
        'imatge': imatge,
        'font': nom_font(url, pagina),
    }


def json_de_resposta(txt):
    txt = txt.strip()
    txt = re.sub(r'^```(json)?', '', txt).strip()
    txt = re.sub(r'```$', '', txt).strip()
    return json.loads(txt)


def resumir(client, titol_font, text_font):
    prompt = (
        "You are the news editor for @onedayonevibe, a hard dance / hardstyle / EDM TikTok account. "
        "It publishes a weekly carousel called 'Top Hard Dance News This Week'. "
        "Write ONE slide for the article below.\n\n"
        "Rules:\n"
        "- Write in English and in your OWN words. Never copy sentences verbatim from the source.\n"
        "- HEADLINE: punchy, max 60 characters, no quotation marks, no trailing period.\n"
        "- SUMMARY: 2 short sentences, max 230 characters in total, factual and neutral tone. "
        "Include the key who/what/when if the article has it.\n\n"
        "Return ONLY a JSON object with this exact shape, nothing else:\n"
        '{"headline": "...", "summary": "..."}\n\n'
        f"SOURCE TITLE: {titol_font}\n\n"
        f"SOURCE TEXT: {text_font[:4000]}"
    )
    m = client.messages.create(model=MODEL, max_tokens=400, messages=[{"role": "user", "content": prompt}])
    d = json_de_resposta(m.content[0].text)
    return d.get('headline', '').strip(), d.get('summary', '').strip()


def caption_final(client, titulars):
    llista = "\n".join(f"- {t}" for t in titulars)
    prompt = (
        "You are the social media editor for @onedayonevibe, a hard dance / hardstyle / EDM TikTok account. "
        "Write the TikTok description for a carousel called 'Top Hard Dance News This Week' that covers these stories:\n"
        f"{llista}\n\n"
        "Rules: CAPTION = one short engaging sentence in English (max 150 characters, no hashtags). "
        "HASHTAGS = exactly 5 relevant lowercase hashtags (no spaces) based on the specific content "
        "(genre, festival, artists), not generic filler.\n"
        'Return ONLY JSON: {"caption": "...", "hashtags": ["#a", "#b", "#c", "#d", "#e"]}'
    )
    m = client.messages.create(model=MODEL, max_tokens=300, messages=[{"role": "user", "content": prompt}])
    d = json_de_resposta(m.content[0].text)
    return d.get('caption', '').strip(), d.get('hashtags', [])


urls = []
for linia in URLS_RAW.replace('\r', '').split('\n'):
    u = linia.strip()
    if u.startswith('http') and u not in urls:
        urls.append(u)
urls = urls[:MAX_NOTICIES]

if not urls:
    print("ERROR: no he rebut cap enllac valid (un per linia, comencant per http)")
    exit(1)
if not ANTHROPIC_KEY:
    print("ERROR: falta ANTHROPIC_KEY")
    exit(1)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
print(f"Notícies a processar: {len(urls)}\n")

noticies = []
for i, url in enumerate(urls, 1):
    print(f"[{i}/{len(urls)}] {url}")
    item = {'url': url, 'source': '', 'headline': '', 'summary': '', 'image_url': '', 'error': ''}
    try:
        info = extreure(url)
        item['source'] = info['font']
        item['image_url'] = info['imatge']
        print(f"   Titol: {info['titol']}")
        print(f"   Text: {len(info['text'])} caracters | foto: {'OK' if info['imatge'] else 'no trobada'} | font: {info['font']}")
        if len(info['text']) < 200:
            item['error'] = "Molt poc text extret (el web pot bloquejar peticions automatitzades). Escriu el titular i el resum a mà."
            item['headline'] = (info['titol'] or '')[:60]
        else:
            item['headline'], item['summary'] = resumir(client, info['titol'], info['text'])
            print(f"   Headline: {item['headline']}")
            print(f"   Summary: {item['summary']}")
    except Exception as e:
        item['error'] = f"No s'ha pogut llegir aquest enllac ({type(e).__name__}). Escriu el titular i el resum a mà."
        print(f"   ERROR: {e}")
    noticies.append(item)

caption, hashtags = '', []
titulars = [n['headline'] for n in noticies if n['headline']]
if titulars:
    try:
        caption, hashtags = caption_final(client, titulars)
        print(f"\nCaption: {caption}\nHashtags: {' '.join(hashtags)}")
    except Exception as e:
        print(f"AVIS: no s'ha pogut generar la descripcio ({e})")

sortida = {
    'generat': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    'stories': noticies,
    'caption': caption,
    'hashtags': hashtags,
}
with open('hardnews_data.json', 'w', encoding='utf-8') as f:
    json.dump(sortida, f, ensure_ascii=False, indent=2)

ok = sum(1 for n in noticies if n['headline'] and n['summary'])
print(f"\nhardnews_data.json escrit! {ok}/{len(noticies)} notícies amb resum")
