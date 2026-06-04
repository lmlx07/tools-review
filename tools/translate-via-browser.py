"""
translate-via-browser.py

Uses CloakBrowser (which has proxy/gateway access to Google) to translate
Chinese markdown posts to English. Runs entirely locally via CDP.

Usage: python scripts/translate-via-browser.py

Output: source_en/_posts/*.md
"""

import json, os, re, sys, time, urllib.request, websocket

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(PROJECT_DIR, 'source', '_posts')
OUT_DIR = os.path.join(PROJECT_DIR, 'source_en', '_posts')
CDP_PORT = 9222
BATCH_SIZE = 8

# ---------- CDP helpers ----------
def cdp_connect():
    tabs = json.loads(urllib.request.urlopen(f'http://localhost:{CDP_PORT}/json', timeout=5).read())
    tab = [t for t in tabs if t.get('type') == 'page']
    if not tab:
        tab = [t for t in tabs if t.get('type') != 'service_worker']
    ws = websocket.create_connection(tab[0]['webSocketDebuggerUrl'], timeout=30)
    _id = [1]

    def cmd(method, params=None):
        _id[0] += 1
        ws.send(json.dumps({'id': _id[0], 'method': method, 'params': params or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get('id') == _id[0]:
                return r.get('result', {})

    def js(expr):
        r = cmd('Runtime.evaluate', {
            'expression': expr,
            'returnByValue': True,
            'awaitPromise': True
        })
        return r.get('result', {}).get('value', '')

    return ws, cmd, js

# ---------- Translate via browser ----------
def translate_batch(texts, from_lang='zh-CN', to_lang='en', js_func=None):
    """Translate a batch of texts using the browser's fetch."""
    if not texts:
        return []

    # Build JS that fetches all texts in parallel
    texts_json = json.dumps(texts, ensure_ascii=False)

    script = f'''
    (async function() {{
        const texts = {texts_json};
        const results = [];
        for (let i = 0; i < texts.length; i++) {{
            try {{
                const url = 'https://translate.googleapis.com/translate_a/single'
                    + '?client=gtx&sl={from_lang}&tl={to_lang}&dt=t'
                    + '&q=' + encodeURIComponent(texts[i]);
                const r = await fetch(url);
                const d = await r.json();
                results.push(d[0].map(p => p[0]).join(''));
            }} catch(e) {{
                results.push('[TRANSLATE_ERROR: ' + e.message.substring(0, 50) + ']');
            }}
        }}
        return JSON.stringify(results);
    }})()
    '''

    result = js_func(script)
    try:
        return json.loads(result)
    except:
        print(f'  [!] Failed to parse translate results: {result[:100]}')
        return texts  # fallback

# ---------- Markdown processing ----------
def parse_front_matter(content):
    """Parse YAML front matter from markdown content."""
    match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    if not match:
        return {}, content

    raw_yaml = match.group(1)
    body = content[match.end():]

    # Simple YAML parser for Hexo front matter
    front = {}
    current_key = None
    current_list = []
    in_list = False

    for line in raw_yaml.split('\n'):
        # List item
        if line.startswith('  - '):
            in_list = True
            current_list.append(line.strip('- ').strip())
            continue
        elif in_list:
            if current_key:
                front[current_key] = current_list
            current_key = None
            current_list = []
            in_list = False

        # Key-value
        m = re.match(r'^(\w+):\s*(.*)', line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if val == '':
                # Could be a list coming
                current_key = key
                current_list = []
                in_list = False
            else:
                front[key] = val

    # Don't forget last list
    if in_list and current_key:
        front[current_key] = current_list

    return front, body

def format_front_matter(front):
    """Convert front matter dict back to YAML string."""
    lines = ['---']
    for key, val in front.items():
        if isinstance(val, list):
            lines.append(f'{key}:')
            for item in val:
                lines.append(f'  - {item}')
        elif isinstance(val, str) and (':' in val or '#' in val):
            lines.append(f'{key}: "{val}"')
        else:
            lines.append(f'{key}: {val}')
    lines.append('---')
    lines.append('')
    return '\n'.join(lines)

def extract_code_blocks(body):
    """Replace code blocks with placeholders, return modified text and blocks list."""
    blocks = []
    idx = [0]

    def replacer(m):
        blocks.append(m.group(0))
        i = idx[0]
        idx[0] += 1
        return f'__CB_{i}__'

    text = re.sub(r'```[\s\S]*?```', replacer, body)
    return text, blocks

def restore_code_blocks(text, blocks):
    for i, block in enumerate(blocks):
        text = text.replace(f'__CB_{i}__', block)
    return text

# ---------- Main ----------
def translate_post(filename, js_func):
    filepath = os.path.join(POSTS_DIR, filename)
    print(f'\n=== {filename} ===')

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Parse front matter
    front, body = parse_front_matter(content)
    print(f'  Front matter keys: {list(front.keys())}')

    # 2. Translate front matter
    if 'title' in front and front['title']:
        trans = translate_batch([front['title']], js_func=js_func)
        if trans:
            front['title_en'] = trans[0]
            print(f'  Title: {front["title"][:30]}... -> {trans[0][:30]}...')

    if 'description' in front and front['description']:
        trans = translate_batch([front['description']], js_func=js_func)
        if trans:
            front['description_en'] = trans[0]

    # 3. Extract code blocks
    body_no_code, code_blocks = extract_code_blocks(body)
    print(f'  Code blocks: {len(code_blocks)}')

    # 4. Split into paragraphs (by double newline)
    paragraphs = re.split(r'\n\n+', body_no_code)

    # 5. Find paragraphs that need translation (non-empty, non-placeholder)
    to_translate = []
    indices = []
    for i, p in enumerate(paragraphs):
        t = p.strip()
        if t and not t.startswith('__CB_'):
            indices.append(i)
            to_translate.append(t)

    print(f'  Paragraphs to translate: {len(to_translate)}')

    # 6. Translate in batches
    all_translated = []
    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i:i + BATCH_SIZE]
        print(f'  Batch {i//BATCH_SIZE + 1}/{(len(to_translate)-1)//BATCH_SIZE + 1} ({len(batch)} texts)...')
        results = translate_batch(batch, js_func=js_func)
        all_translated.extend(results)
        time.sleep(0.3)

    # 7. Reassemble
    result_paragraphs = list(paragraphs)
    for idx_in_para, translated in zip(indices, all_translated):
        result_paragraphs[idx_in_para] = translated

    translated_body = '\n\n'.join(result_paragraphs)
    translated_body = restore_code_blocks(translated_body, code_blocks)

    # 8. Build new front matter
    new_front = {'lang': 'en'}
    for key, val in front.items():
        if key == 'title':
            new_front['title'] = front.get('title_en', front['title'])
        elif key == 'description':
            new_front['description'] = front.get('description_en', front['description'])
        elif key == 'title_en' or key == 'description_en':
            continue
        else:
            new_front[key] = val

    # 9. Write output
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, filename)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(format_front_matter(new_front) + '\n' + translated_body)

    print(f'  -> Done: source_en/_posts/{filename}')
    return True

def main():
    print('=== Translate Blog Posts via CloakBrowser ===')

    # Connect via CDP
    print(f'Connecting to CloakBrowser on port {CDP_PORT}...')
    ws, cmd, js = cdp_connect()
    print('Connected!')

    # Open a blank page to execute translations
    cmd('Page.enable')
    tabs = json.loads(urllib.request.urlopen(f'http://localhost:{CDP_PORT}/json', timeout=5).read())

    # Navigate to about:blank
    cmd('Page.navigate', {'url': 'about:blank'})
    time.sleep(1)

    # Verify we can translate
    test = translate_batch(['你好世界'], js_func=js)
    print(f'Test translation: "你好世界" -> "{test[0] if test else "FAILED"}"')

    if not test or 'TRANSLATE_ERROR' in str(test):
        print('ERROR: Translation API not accessible even via browser!')
        ws.close()
        return

    # Get all posts
    files = sorted([f for f in os.listdir(POSTS_DIR) if f.endswith('.md') and not f.startswith('_')])
    print(f'\nFound {len(files)} posts to translate\n')

    # Translate each post
    success = 0
    for filename in files:
        try:
            if translate_post(filename, js):
                success += 1
        except Exception as e:
            print(f'  ERROR: {e}')

    print(f'\n=== Done: {success}/{len(files)} posts translated ===')
    print(f'Output: {OUT_DIR}')

    ws.close()

if __name__ == '__main__':
    main()
