#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PAPERLESS_DIR="${PAPERLESS_DIR:-$HOME/paperless}"

if [[ $# -gt 0 && "$1" == "--paperless-dir" ]]; then
  [[ $# -ge 2 ]] || { echo "ERROR: --paperless-dir needs a path" >&2; exit 1; }
  PAPERLESS_DIR="$2"
  shift 2
fi

compose_file=""
for candidate in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
  if [[ -f "$PAPERLESS_DIR/$candidate" ]]; then
    compose_file="$PAPERLESS_DIR/$candidate"
    break
  fi
done

if [[ -z "$compose_file" ]]; then
  echo "ERROR: no Paperless Docker Compose file found in $PAPERLESS_DIR" >&2
  echo "Use PAPERLESS_DIR=/path/to/paperless or --paperless-dir /path/to/paperless" >&2
  exit 1
fi

export CLASSIFIER_DIR="$SCRIPT_DIR"
DC=(docker compose --project-directory "$PAPERLESS_DIR" -f "$compose_file" -f "$SCRIPT_DIR/docker-compose.classifier.yml")

cmd="${1:-help}"
shift || true

case "$cmd" in
  logs)
    exec "${DC[@]}" logs -f --tail=100 paperless-classifier
    ;;
  status)
    exec "${DC[@]}" ps paperless-classifier
    ;;
  start)
    exec "${DC[@]}" up -d paperless-classifier
    ;;
  stop)
    exec "${DC[@]}" stop paperless-classifier
    ;;
  restart)
    exec "${DC[@]}" restart paperless-classifier
    ;;
  sync)
    "${DC[@]}" run --rm paperless-classifier python /app/classifier.py validate
    "${DC[@]}" run --rm paperless-classifier python /app/classifier.py sync
    exec "${DC[@]}" restart paperless-classifier
    ;;
  once)
    exec "${DC[@]}" run --rm paperless-classifier python /app/classifier.py once
    ;;
  classify)
    [[ $# -eq 1 ]] || { echo "Usage: ./classifierctl.sh classify DOCUMENT_ID" >&2; exit 1; }
    exec "${DC[@]}" run --rm paperless-classifier python /app/classifier.py classify "$1"
    ;;
  validate)
    exec "${DC[@]}" run --rm paperless-classifier python /app/classifier.py validate
    ;;
  build)
    exec "${DC[@]}" build paperless-classifier
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage: ./classifierctl.sh [--paperless-dir PATH] COMMAND

Commands:
  status       Show classifier status
  logs         Follow classifier logs
  start        Start the classifier
  stop         Stop the classifier
  restart      Restart the classifier
  sync         Validate + sync taxonomy, then restart
  once         Process all unseen/changed documents once
  classify ID  Reclassify one Paperless document
  validate     Validate taxonomy.yaml
  build        Rebuild the classifier image

Default Paperless path: ~/paperless
Override with PAPERLESS_DIR=/path or --paperless-dir /path.
EOF
    ;;
  *)
    echo "ERROR: unknown command: $cmd" >&2
    echo "Run ./classifierctl.sh help" >&2
    exit 1
    ;;
esac
