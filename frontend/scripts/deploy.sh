#!/bin/bash
# Deploy CQA Report to Vercel
# Usage: ./scripts/deploy.sh [--prod]

set -e

echo "[CQA] Building static site..."
npm run build

if [ "$1" = "--prod" ]; then
    echo "[CQA] Deploying to Vercel (production)..."
    npx vercel deploy dist/ --yes --prod
else
    echo "[CQA] Deploying to Vercel (preview)..."
    npx vercel deploy dist/ --yes
fi

echo "[CQA] Deploy complete!"
