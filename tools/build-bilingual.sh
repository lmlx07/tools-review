#!/bin/bash
# build-bilingual.sh
# Dual-build script: generates Chinese and English versions, merges into public/

set -e
cd "$(dirname "$0")/.."

echo "=== Step 1: Build Chinese site ==="
npx hexo clean
npx hexo generate --config _config.yml
# Rename to avoid conflict
mv public public-zh

echo ""
echo "=== Step 2: Build English site ==="
npx hexo generate --config _config.en.yml
# English site is already in public-en/ (set in _config.en.yml)

echo ""
echo "=== Step 3: Merge English into Chinese site ==="
# Start with Chinese
mkdir -p public
cp -r public-zh/* public/
# Add English under /en/
mkdir -p public/en
cp -r public-en/* public/en/

echo ""
echo "=== Step 4: Clean up ==="
rm -rf public-zh public-en

echo ""
echo "=== Done! public/ contains both languages ==="
echo "  / → Chinese"
echo "  /en/ → English"
echo ""
echo "Run 'npx hexo deploy' to publish."
