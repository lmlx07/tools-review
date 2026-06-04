"""
postprocess-en-posts.py
Fix tags, categories, and remove hardcoded TOC from English posts.
"""
import os, re

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(PROJECT_DIR, 'source_en', '_posts')

# Tag/category translation mapping
TRANSLATIONS = {
    '浏览器自动化': 'Browser Automation',
    '反检测': 'Anti-Detection',
    '浏览器指纹': 'Browser Fingerprinting',
    '网络拦截': 'Network Interception',
    '爬虫': 'Web Scraping',
    '性能优化': 'Performance Optimization',
    'CDP 基础': 'CDP Basics',
    'Python 实战': 'Python Practice',
}

def fix_front_matter(content):
    """Translate tags and categories in front matter."""
    lines = content.split('\n')
    in_front = False
    result = []

    for line in lines:
        if line.startswith('---'):
            in_front = not in_front
            result.append(line)
            continue
        if not in_front:
            result.append(line)
            continue

        m = re.match(r'^(\s*-\s+)(.*)', line)
        if m:
            prefix, val = m.group(1), m.group(2)
            if val in TRANSLATIONS:
                result.append(f'{prefix}{TRANSLATIONS[val]}')
            else:
                result.append(line)
        else:
            result.append(line)

    return '\n'.join(result)

def remove_toc_and_cleanup(content):
    """Remove hardcoded TOC sections and clean up double separators."""
    # Remove TOC section (from ## Table of contents to next ## or ---)
    content = re.sub(
        r'## (Table of contents|目录)\n\n[\s\S]*?\n\n(?=## |---|\Z)',
        '', content
    )

    # Remove double --- separators (from TOC removal leaving ---\n\n---)
    content = re.sub(r'---\n\n(\s*---)', r'\1', content)

    # Remove triple+ --- sequences
    while '---\n---' in content or '---\n\n---' in content:
        content = re.sub(r'---(\s*\n\s*)+---', '---', content)

    return content

def main():
    files = sorted([f for f in os.listdir(POSTS_DIR) if f.endswith('.md')])
    print('Post-processing English posts...')

    for fname in files:
        fpath = os.path.join(POSTS_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content

        content = fix_front_matter(content)
        content = remove_toc_and_cleanup(content)

        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'  Updated: {fname}')
        else:
            print(f'  No changes: {fname}')

    print('Done!')

if __name__ == '__main__':
    main()
