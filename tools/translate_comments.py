"""
Translate Chinese comments in code blocks via MyMemory API (free, no key needed).
Processes one code block at a time, re-scanning content after each change.
"""
import json, os, re, sys, time
from deep_translator import GoogleTranslator

sys.stdout.reconfigure(encoding='utf-8')
POSTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'source_en', '_posts')

# Shared translator instance
_translator = None

def get_translator():
    global _translator
    if _translator is None:
        _translator = GoogleTranslator(source='zh-CN', target='en')
    return _translator


def translate_single(text, retries=2):
    """Translate a single Chinese text via Google Translate. Returns translated string or None."""
    for attempt in range(retries):
        try:
            result = get_translator().translate(text)
            if result and result != text:
                return result
            return None
        except Exception as e:
            err_msg = str(e)
            if attempt < retries - 1:
                wait = 3 * (attempt + 1)
                print(f'\n      [Retry in {wait}s: {err_msg[:60]}]')
                time.sleep(wait)
            else:
                print(f'      [Error] {err_msg[:80]}')
                return None
    return None


def has_chinese_comment(line):
    s = line.strip()
    if not s:
        return None

    indent = line[:len(line) - len(s)]

    # Standalone comment lines (start with #, //, or """)
    if s.startswith('# ') and not s.startswith('#!'):
        t = s[2:].strip()
        p = '# '
        before = ''
    elif s.startswith('#') and not s.startswith('#!'):
        t = s[1:].strip()
        p = '# '
        before = ''
    elif s.startswith('// '):
        t = s[3:].strip()
        p = '// '
        before = ''
    elif s.startswith('//'):
        t = s[2:].strip()
        p = '// '
        before = ''
    elif s.startswith('"""') and s.endswith('"""') and len(s) > 6:
        t = s[3:-3].strip()
        p = '"""'
        before = ''
    else:
        # Inline comments: code  # Chinese or code  // Chinese
        m = re.search(r'(# |// )(.*)$', s)
        if m:
            before = s[:m.start(1)].rstrip()
            p = ' ' + m.group(1)
            t = m.group(2).strip()
        else:
            return None

    if t and re.search(r'[一-鿿]', t):
        return {'text': t, 'prefix': p, 'before': before, 'indent': indent}
    return None


def process_file(fpath):
    content = open(fpath, 'r', encoding='utf-8').read()
    orig = content
    total_done = 0

    cursor = 0
    while True:
        # Find first code block with Chinese comments after cursor
        cb = None
        for m in re.finditer(r'```(\w*)\n(.*?)```', content[cursor:], re.DOTALL):
            code = m.group(2)
            lines = code.split('\n')
            has_cn = any(has_chinese_comment(line) for line in lines)
            if has_cn:
                cb = (cursor + m.start(), cursor + m.end(), m.group(0), m.group(1), m.group(2))
                break

        if not cb:
            break

        start, end, full_block, lang, code = cb
        lines = code.split('\n')

        # Collect Chinese comments in this block
        to_translate = []
        indices = []
        for li, line in enumerate(lines):
            info = has_chinese_comment(line)
            if info:
                indices.append(li)
                to_translate.append(info)

        # Translate each text
        changed = False
        for li, info in zip(indices, to_translate):
            print(f'    Translating: {info["text"][:50]}...', end=' ')
            trans = translate_single(info['text'])
            if trans:
                if info['prefix'] == '"""':
                    lines[li] = info['indent'] + '"""' + trans + '"""'
                else:
                    lines[li] = info['indent'] + info['before'] + info['prefix'] + trans
                print(f'-> {trans[:50]}')
                changed = True
                total_done += 1
            else:
                print('(skipped)')
            time.sleep(0.3)  # Rate limiting

        if not changed:
            break

        new_code = '\n'.join(lines)
        new_block = f'```{lang}\n{new_code}\n```'
        content = content[:start] + new_block + content[end:]
        cursor = start + len(new_block)

    if content != orig:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        return total_done
    return 0


def main():
    print('=== Translate Code Comments in English Posts ===')
    print(f'Posts directory: {POSTS_DIR}\n')

    for fn in sorted(os.listdir(POSTS_DIR)):
        if not fn.endswith('.md'):
            continue
        fpath = os.path.join(POSTS_DIR, fn)
        print(f'Processing: {fn}')
        n = process_file(fpath)
        if n:
            print(f'  => translated {n} comments\n')
        else:
            print(f'  => no changes\n')

    print('Done!')


if __name__ == '__main__':
    main()
