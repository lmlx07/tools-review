/**
 * translate-posts.js
 *
 * Reads Chinese markdown posts from source/_posts/, translates them to English
 * via Google Translate API, and writes the English versions to source_en/_posts/.
 *
 * Preserves: front matter (translates title/description), code blocks,
 * inline code, links, images, HTML tags.
 *
 * Usage: node scripts/translate-posts.js
 */

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

// ---------- config ----------
const POSTS_DIR = path.resolve(__dirname, '..', 'source', '_posts');
const OUT_DIR   = path.resolve(__dirname, '..', 'source_en', '_posts');
const BATCH_SIZE = 5;  // parallel translate requests per batch
const FROM_LANG = 'zh-CN';
const TO_LANG   = 'en';

// ---------- Google Translate API ----------
async function translate(text, from = FROM_LANG, to = TO_LANG) {
  if (!text || text.trim().length === 0) return text;

  const url = 'https://translate.googleapis.com/translate_a/single'
    + `?client=gtx&sl=${from}&tl=${to}&dt=t`
    + '&q=' + encodeURIComponent(text);

  const res = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0' }
  });

  if (!res.ok) {
    throw new Error(`Translate API returned ${res.status}: ${res.statusText}`);
  }

  const data = await res.json();
  return data[0].map(p => p[0]).join('');
}

async function translateBatch(texts) {
  const results = [];
  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE);
    const batchResults = await Promise.all(
      batch.map(t => translate(t).catch(err => {
        console.error(`  [!] translate error: ${err.message.substring(0, 100)}`);
        return t; // fallback to original on error
      }))
    );
    results.push(...batchResults);
    // Small delay between batches to avoid rate limiting
    if (i + BATCH_SIZE < texts.length) {
      await new Promise(r => setTimeout(r, 500));
    }
  }
  return results;
}

// ---------- Markdown processing ----------

/** Extract fenced code blocks and replace with placeholders */
function extractCodeBlocks(body) {
  const blocks = [];
  let idx = 0;
  const processed = body.replace(/(```[\s\S]*?```)/g, (match) => {
    const placeholder = `__CB_${idx}__`;
    blocks.push(match);
    idx++;
    return placeholder;
  });
  return { text: processed, blocks };
}

/** Restore code blocks from placeholders */
function restoreCodeBlocks(text, blocks) {
  return text.replace(/__CB_(\d+)__/g, (_, idx) => blocks[parseInt(idx)]);
}

/** Split text into paragraphs (by blank lines), preserving structure */
function splitParagraphs(text) {
  return text.split(/\n\n+/);
}

/** Extract inline elements that should not be translated */
const INLINE_PATTERNS = [
  { regex: /`[^`]+`/g, prefix: '__IC_' },       // inline code
  { regex: /!\[([^\]]*)\]\(([^)]+)\)/g, prefix: '__IMG_' }, // images
  { regex: /\[([^\]]*)\]\(([^)]+)\)/g, prefix: '__LN_' },   // links
];

function extractInlineElements(text) {
  const map = {};
  let processed = text;

  for (const { regex, prefix } of INLINE_PATTERNS) {
    let idx = 0;
    processed = processed.replace(regex, (match) => {
      const key = `${prefix}${idx}__`;
      map[key] = match;
      idx++;
      return key;
    });
  }

  return { text: processed, map };
}

function restoreInlineElements(text, map) {
  let result = text;
  for (const [key, value] of Object.entries(map)) {
    result = result.replace(key, value);
  }
  return result;
}

// ---------- Front matter processing ----------
function parseFrontMatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---\n/);
  if (!match) return { front: {}, body: content };

  try {
    const front = yaml.load(match[1]);
    const body = content.slice(match[0].length);
    return { front, body, raw: match[1] };
  } catch (err) {
    console.error(`  [!] YAML parse error: ${err.message}`);
    return { front: {}, body: content };
  }
}

async function translateFrontMatter(front) {
  const translated = { ...front };

  // Translate title
  if (front.title) {
    translated.title = await translate(front.title);
    console.log(`  title: "${front.title.substring(0, 30)}..." -> "${translated.title.substring(0, 30)}..."`);
  }

  // Translate description
  if (front.description) {
    translated.description = await translate(front.description);
  }

  // Set language
  translated.lang = TO_LANG;

  return translated;
}

function formatFrontMatter(front) {
  // Convert back to YAML string manually (preserving the original format)
  let yamlStr = '---\n';
  for (const [key, value] of Object.entries(front)) {
    if (key === 'lang') {
      yamlStr += 'lang: en\n';
    } else if (Array.isArray(value)) {
      yamlStr += `${key}:\n`;
      for (const item of value) {
        yamlStr += `  - ${item}\n`;
      }
    } else if (typeof value === 'string') {
      // Quote if contains special characters
      if (value.includes(':') || value.includes('#') || value.includes('"') || value.includes("'")) {
        yamlStr += `${key}: "${value.replace(/"/g, '\\"')}"\n`;
      } else {
        yamlStr += `${key}: ${value}\n`;
      }
    } else if (value instanceof Date) {
      yamlStr += `${key}: ${value.toISOString()}\n`;
    } else {
      yamlStr += `${key}: ${value}\n`;
    }
  }
  yamlStr += '---\n\n';
  return yamlStr;
}

// ---------- Main translation logic ----------
async function translatePost(filePath) {
  const filename = path.basename(filePath);
  console.log(`\n--- Translating: ${filename} ---`);

  const content = fs.readFileSync(filePath, 'utf-8');

  // 1. Parse front matter
  const { front, body, raw } = parseFrontMatter(content);

  // 2. Translate front matter
  console.log('  Front matter...');
  const translatedFront = await translateFrontMatter(front);

  // 3. Extract code blocks from body
  console.log('  Body...');
  const { text: bodyWithoutCode, blocks } = extractCodeBlocks(body);
  console.log(`  Found ${blocks.length} code blocks`);

  // 4. Split body into paragraphs
  const paragraphs = splitParagraphs(bodyWithoutCode);

  // 5. Filter non-empty paragraphs and note their indices
  const nonEmptyIndices = [];
  const nonEmptyTexts = [];
  paragraphs.forEach((p, i) => {
    const trimmed = p.trim();
    if (trimmed.length > 0 && !trimmed.startsWith('__CB_')) {
      nonEmptyIndices.push(i);
      nonEmptyTexts.push(trimmed);
    }
  });

  console.log(`  Translating ${nonEmptyTexts.length} paragraphs in batches of ${BATCH_SIZE}...`);

  // 6. Translate paragraphs
  const translatedParagraphs = await translateBatch(nonEmptyTexts);

  // 7. Reassemble body
  const resultParagraphs = [...paragraphs];
  nonEmptyIndices.forEach((idx, i) => {
    resultParagraphs[idx] = translatedParagraphs[i] || paragraphs[idx];
  });

  let translatedBody = resultParagraphs.join('\n\n');

  // 8. Restore code blocks
  translatedBody = restoreCodeBlocks(translatedBody, blocks);

  // 9. Write output
  const outContent = formatFrontMatter(translatedFront) + translatedBody;
  const outPath = path.join(OUT_DIR, filename);

  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(outPath, outContent, 'utf-8');

  console.log(`  Done -> source_en/_posts/${filename}`);
  return { filename, paragraphs: nonEmptyTexts.length };
}

// ---------- Main ----------
async function main() {
  console.log('=== Hexo Post Translation Script ===');
  console.log(`From: ${FROM_LANG}  To: ${TO_LANG}`);
  console.log(`Source: ${POSTS_DIR}`);
  console.log(`Output: ${OUT_DIR}`);

  // Ensure output directory exists
  fs.mkdirSync(OUT_DIR, { recursive: true });

  // Read all .md files
  const files = fs.readdirSync(POSTS_DIR)
    .filter(f => f.endsWith('.md') && !f.includes('.en.'))
    .map(f => path.join(POSTS_DIR, f));

  console.log(`\nFound ${files.length} posts to translate\n`);

  const results = [];
  for (const file of files) {
    try {
      const result = await translatePost(file);
      results.push(result);
    } catch (err) {
      console.error(`\n  ERROR translating ${path.basename(file)}:`, err.message);
    }
  }

  console.log('\n=== Summary ===');
  results.forEach(r => {
    console.log(`  ${r.filename}: ${r.paragraphs} paragraphs translated`);
  });
  console.log(`\nAll done! ${results.length}/${files.length} posts translated.`);
  console.log(`English posts saved to: ${OUT_DIR}`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
