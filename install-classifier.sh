#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PAPERLESS_DIR="${1:-${PAPERLESS_DIR:-$HOME/paperless}}"

if [[ ! -d "$PAPERLESS_DIR" ]]; then
  echo "ERROR: Paperless directory not found: $PAPERLESS_DIR" >&2
  echo "Usage: ./install-classifier.sh [path-to-paperless]" >&2
  exit 1
fi

compose_file=""
for candidate in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
  if [[ -f "$PAPERLESS_DIR/$candidate" ]]; then
    compose_file="$PAPERLESS_DIR/$candidate"
    break
  fi
done

if [[ -z "$compose_file" ]]; then
  echo "ERROR: no Docker Compose file found in $PAPERLESS_DIR" >&2
  echo "Expected one of: docker-compose.yml, docker-compose.yaml, compose.yml, compose.yaml" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/docker-compose.classifier.yml" || ! -d "$SCRIPT_DIR/classifier" ]]; then
  echo "ERROR: classifier repository is incomplete." >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.classifier.env" ]]; then
  cp "$SCRIPT_DIR/.classifier.env.example" "$SCRIPT_DIR/.classifier.env"
  chmod 600 "$SCRIPT_DIR/.classifier.env"
  echo "Created $SCRIPT_DIR/.classifier.env"
  echo "Add your PAPERLESS_TOKEN and OPENAI_API_KEY, then run this command again:"
  echo "  ./install-classifier.sh '$PAPERLESS_DIR'"
  exit 2
fi

if grep -Eq 'PASTE_(PAPERLESS_API_TOKEN|OPENAI_API_KEY)_HERE' "$SCRIPT_DIR/.classifier.env"; then
  echo "ERROR: .classifier.env still contains placeholder credentials." >&2
  echo "Edit: $SCRIPT_DIR/.classifier.env" >&2
  exit 2
fi
chmod 600 "$SCRIPT_DIR/.classifier.env"

export CLASSIFIER_DIR="$SCRIPT_DIR"
DC=(docker compose --project-directory "$PAPERLESS_DIR" -f "$compose_file" -f "$SCRIPT_DIR/docker-compose.classifier.yml")

echo "Paperless:  $PAPERLESS_DIR"
echo "Classifier: $SCRIPT_DIR"
echo

echo "Building classifier..."
"${DC[@]}" build paperless-classifier

echo "Validating taxonomy..."
"${DC[@]}" run --rm paperless-classifier python /app/classifier.py validate

echo "Synchronizing taxonomy with Paperless..."
"${DC[@]}" run --rm paperless-classifier python /app/classifier.py sync

echo "Starting classifier..."
"${DC[@]}" up -d paperless-classifier

echo
"${DC[@]}" ps paperless-classifier
echo
echo "Installed successfully."
echo "Logs: ./classifierctl.sh logs"
