"""
translate-code-comments.py
Translate Chinese comments inside code blocks in English markdown posts.
Uses Google Translate via CloakBrowser CDP.
"""
import json, os, re, sys, time, urllib.request, websocket

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(PROJECT_DIR, 'source_en', '_posts')
CDP_PORT = 9222

def cdp_connect():
    tabs = json.loads(urllib.request.urlopen(f'http://localhost:{CDP_PORT}/json', timeout=5).read())
    tab = [t for t in tabs if t.get('type') == 'page']
    if not tab:
        tab = [t for t in tabs if t.get('type') != 'service_worker']
    ws = websocket.create_connection(tab[0]['webSocketDebuggerUrl'], timeout=120)
    ws.settimeout(120)
    _id = [1]
    def cmd(method, params=None):
        _id[0] += 1
        ws.send(json.dumps({'id': _id[0], 'method': method, 'params': params or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get('id') == _id[0]:
                return r.get('result', {})
    def js(expr):
        r = cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
        return r.get('result', {}).get('value', '')
    return ws, cmd, js

def translate_batch(texts, js_func=None):
    if not texts:
        return []
    texts_json = json.dumps(texts, ensure_ascii=False)
    script = f'''
    (async function() {{
        const texts = {texts_json};
        const results = await Promise.all(texts.map(async (t) => {{
            try {{
                const url = 'https://translate.googleapis.com/translate_a/single'
                    + '?client=gtx&sl=zh-CN&tl=en&dt=t'
                    + '&q=' + encodeURIComponent(t);
                const r = await fetch(url);
                const d = await r.json();
                return d[0].map(p => p[0]).join('');
            }} catch(e) {{
                return null;
            }}
        }}));
        return JSON.stringify(results);
    }})()
    '''
    result = js_func(script)
    try: return json.loads(result)
    except: return []

def main():
    print('=== Translate Code Comments ===')
    ws, cmd, js = cdp_connect()
    print('Connected!')

    for fname in sorted(os.listdir(POSTS_DIR)):
        if not fname.endswith('.md'): continue
        fpath = os.path.join(POSTS_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        orig = content

        print(f'\n=== {fname} ===')
        code_blocks = list(re.finditer(r'```(\w*)\n(.*?)```', content, re.DOTALL))
        if not code_blocks: continue

        # Collect all Chinese comment lines across all code blocks
        jobs = []  # (cb_index, line_index, old_line, prefix, comment_text)
        for ci, cb in enumerate(code_blocks):
            lines = cb.group(2).split('\n')
            for li, line in enumerate(lines):
                s = line.strip()
                if not s: continue
                comment = None; prefix = ''
                if s.startswith('# ') and not s.startswith('#!'):
                    comment = s[2:].strip(); prefix = '# '
                elif s.startswith('#') and not s.startswith('#!'):
                    comment = s[1:].strip(); prefix = '# '
                elif s.startswith('// '):
                    comment = s[3:].strip(); prefix = '// '
                elif s.startswith('//'):
                    comment = s[2:].strip(); prefix = '// '
                elif s.startswith('"""') and s.endswith('"""') and len(s) > 6:
                    comment = s[3:-3].strip(); prefix = '"""'
                if comment and re.search(r'[一-鿿]', comment):
                    jobs.append((ci, li, line, prefix, comment))

        if not jobs:
            print('  No Chinese comments.')
            continue

        print(f'  {len(jobs)} Chinese comment lines found.')

        # Translate in batches to avoid timeout
        translations = []
        BATCH_SIZE = 8
        for i in range(0, len(jobs), BATCH_SIZE):
            batch_texts = [j[4] for j in jobs[i:i+BATCH_SIZE]]
            print(f'  Batch {i//BATCH_SIZE+1}/{(len(jobs)-1)//BATCH_SIZE+1} ({len(batch_texts)} texts)...')
            batch_results = translate_batch(batch_texts, js_func=js)
            translations.extend(batch_results)
            time.sleep(0.5)

        # Group replacements by code block
        block_map = {}  # ci -> {li -> new_line}
        for (ci, li, old_line, prefix, orig_text), trans in zip(jobs, translations):
            if not trans or trans == orig_text: continue
            indent = old_line[:len(old_line) - len(old_line.strip())]
            if prefix == '"""':
                new_line = indent + '"""' + trans + '"""'
            else:
                new_line = indent + prefix + trans
            block_map.setdefault(ci, {})[li] = new_line

        if not block_map:
            print('  No useful translations.')
            continue

        # Apply (iterate in reverse to preserve positions)
        for ci in sorted(block_map.keys(), reverse=True):
            cb = code_blocks[ci]
            lines = cb.group(2).split('\n')
            for li, new_line in block_map[ci].items():
                lines[li] = new_line
            new_block = '```' + cb.group(1) + '\n' + '\n'.join(lines) + '\n```'
            content = content[:cb.start()] + new_block + content[cb.end():]

        if content != orig:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            n = sum(len(v) for v in block_map.values())
            print(f'  Translated {n} comments across {len(block_map)} code blocks.')
        else:
            print('  No changes.')

    print('\nDone!')
    ws.close()

if __name__ == '__main__':
    main()
