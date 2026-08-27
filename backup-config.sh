#!/usr/bin/env bash
set -euo pipefail

# Run from the repository root. This intentionally backs up only classifier
# source/config files that are safe to version. It never copies .classifier.env.
SOURCE_DIR="${1:-$HOME/paperless}"

required=(
  "$SOURCE_DIR/classifier/classifier.py"
  "$SOURCE_DIR/classifier/taxonomy.yaml"
  "$SOURCE_DIR/classifier/Dockerfile"
  "$SOURCE_DIR/classifier/requirements.txt"
  "$SOURCE_DIR/docker-compose.classifier.yml"
  "$SOURCE_DIR/install-classifier.sh"
  "$SOURCE_DIR/.classifier.env.example"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "ERROR: missing $f" >&2; exit 1; }
done

mkdir -p classifier
cp "$SOURCE_DIR/classifier/classifier.py" classifier/
cp "$SOURCE_DIR/classifier/taxonomy.yaml" classifier/
cp "$SOURCE_DIR/classifier/Dockerfile" classifier/
cp "$SOURCE_DIR/classifier/requirements.txt" classifier/
cp "$SOURCE_DIR/docker-compose.classifier.yml" ./
cp "$SOURCE_DIR/install-classifier.sh" ./
cp "$SOURCE_DIR/.classifier.env.example" ./
chmod +x install-classifier.sh

./verify-no-secrets.sh

echo "Safe classifier config copied from $SOURCE_DIR."
echo "Review with: git diff"
