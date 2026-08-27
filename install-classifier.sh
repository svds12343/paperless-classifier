#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f docker-compose.yml ]]; then
  echo "ERROR: run this from your existing ~/paperless directory." >&2
  exit 1
fi
if [[ ! -f docker-compose.classifier.yml || ! -d classifier ]]; then
  echo "ERROR: classifier bundle is incomplete." >&2
  exit 1
fi

if [[ ! -f .classifier.env ]]; then
  cp .classifier.env.example .classifier.env
  chmod 600 .classifier.env
  echo "Created .classifier.env."
  echo "Set PAPERLESS_TOKEN and OPENAI_API_KEY in it, then rerun ./install-classifier.sh"
  exit 2
fi

if grep -Eq 'PASTE_(PAPERLESS_API_TOKEN|OPENAI_API_KEY)_HERE' .classifier.env; then
  echo "ERROR: .classifier.env still contains placeholder secrets." >&2
  exit 2
fi
chmod 600 .classifier.env

DC=(docker compose -f docker-compose.yml -f docker-compose.classifier.yml)

echo "Building classifier..."
"${DC[@]}" build paperless-classifier

echo "Validating taxonomy..."
"${DC[@]}" run --rm paperless-classifier python /app/classifier.py validate

echo "Synchronizing tags, document types and storage paths..."
"${DC[@]}" run --rm paperless-classifier python /app/classifier.py sync

echo "Starting classifier..."
"${DC[@]}" up -d paperless-classifier

echo
"${DC[@]}" ps paperless-classifier
echo
echo "Logs:"
echo "docker compose -f docker-compose.yml -f docker-compose.classifier.yml logs -f --tail=100 paperless-classifier"
