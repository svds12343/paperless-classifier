#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PAPERLESS_DIR="${1:-${PAPERLESS_DIR:-$HOME/paperless}}"
ENV_FILE="$SCRIPT_DIR/.classifier.env"

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

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$SCRIPT_DIR/.classifier.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE"
  echo "Review and configure the entire file before first start, then run:"
  echo "  ./install-classifier.sh '$PAPERLESS_DIR'"
  exit 2
fi

required_keys=(
  PAPERLESS_URL
  PAPERLESS_TOKEN
  OPENAI_API_KEY
  OPENAI_MODEL
  OPENAI_BASE_URL
  OPENAI_REASONING_EFFORT
  POLL_INTERVAL
  REQUEST_TIMEOUT
  MAX_TEXT_CHARS
  MIN_CONFIDENCE
  CORRESPONDENT_FUZZY_THRESHOLD
  ERROR_RETRY_SECONDS
  BOOTSTRAP_EXISTING
  TITLE_LANGUAGE
  LOG_LEVEL
  TAXONOMY_FILE
  STATE_FILE
)

missing_keys=()
empty_keys=()
for key in "${required_keys[@]}"; do
  if ! grep -Eq "^[[:space:]]*${key}=" "$ENV_FILE"; then
    missing_keys+=("$key")
  elif grep -Eq "^[[:space:]]*${key}=[[:space:]]*$" "$ENV_FILE"; then
    empty_keys+=("$key")
  fi
done

if (( ${#missing_keys[@]} > 0 )); then
  echo "ERROR: .classifier.env is missing configuration keys:" >&2
  printf '  - %s\n' "${missing_keys[@]}" >&2
  echo "Restore them from .classifier.env.example and review the complete file." >&2
  exit 2
fi

if (( ${#empty_keys[@]} > 0 )); then
  echo "ERROR: .classifier.env contains empty configuration values:" >&2
  printf '  - %s\n' "${empty_keys[@]}" >&2
  echo "Set every value before starting the classifier." >&2
  exit 2
fi

if grep -Eq 'PASTE_(PAPERLESS_API_TOKEN|OPENAI_API_KEY)_HERE' "$ENV_FILE"; then
  echo "ERROR: .classifier.env still contains placeholder credentials." >&2
  echo "Edit: $ENV_FILE" >&2
  exit 2
fi

chmod 600 "$ENV_FILE"

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
