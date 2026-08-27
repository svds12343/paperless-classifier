#!/usr/bin/env bash
set -euo pipefail

for f in .classifier.env docker-compose.env .env; do
  if [[ -f "$f" ]]; then
    echo "ERROR: secret/runtime file present: $f" >&2
    exit 1
  fi
done

# OpenAI-style live API keys should never be in source.
if grep -RInE --exclude-dir=.git --exclude-dir=__pycache__ --exclude='*.pyc' 'sk-[A-Za-z0-9_-]{20,}' .; then
  echo "ERROR: possible OpenAI API key found." >&2
  exit 1
fi

# Detect non-placeholder values in env-style assignments.
while IFS= read -r line; do
  case "$line" in
    *'.classifier.env.example:'*'PAPERLESS_TOKEN=PASTE_PAPERLESS_API_TOKEN_HERE'*) ;;
    *'.classifier.env.example:'*'OPENAI_API_KEY=PASTE_OPENAI_API_KEY_HERE'*) ;;
    *'README.md:'*'PAPERLESS_TOKEN=<new Paperless API token>'*) ;;
    *'README.md:'*'PAPERLESS_TOKEN=...'*) ;;
    *'README.md:'*'OPENAI_API_KEY=<OpenAI API key>'*) ;;
    *'README.md:'*'OPENAI_API_KEY=...'*) ;;
    *'verify-no-secrets.sh:'*) ;;
    *)
      echo "$line"
      echo "ERROR: possible live token assignment found." >&2
      exit 1
      ;;
  esac
done < <(grep -RInE --exclude-dir=.git --exclude-dir=__pycache__ --exclude='*.pyc' '(PAPERLESS_TOKEN|OPENAI_API_KEY)=' . || true)

echo "No obvious secrets found. Still review 'git diff --cached' before pushing."
