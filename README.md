# Paperless-ngx Strict AI Classifier

A Docker sidecar for Paperless-ngx that classifies every new document with OpenAI while keeping the taxonomy under hard control.

## What it does

- Automatically creates/synchronizes approved document types, nested tags and storage paths from `taxonomy.yaml`.
- Polls Paperless for new documents after OCR; no Paperless workflow is required.
- Sends only extracted OCR/text to OpenAI, not the original PDF.
- Uses the OpenAI Responses API with strict JSON Schema Structured Outputs and `store=false`.
- The model can only return document type/category/tag codes that exist in `taxonomy.yaml`.
- Validates the result a second time in code before changing Paperless.
- Automatically creates new correspondents when genuinely new and reuses known/aliased correspondents.
- Preserves manual tags outside the classifier-managed taxonomy.
- Sets title, document type, tags, correspondent, date when reliable, and storage path.
- Adds `AI::Classé` after success, `AI::À vérifier` when uncertain, and `AI::Erreur` on technical failure.
- Technical failures retry after a cooldown; ambiguous documents are not repeatedly charged.
- Stores processing state in a Docker volume and reprocesses a document if its extracted content changes.
- With `BOOTSTRAP_EXISTING=true`, existing documents are classified on first startup too.

## Repository layout

```text
paperless-classifier/
├── .classifier.env.example
├── .gitignore
├── README.md
├── backup-config.sh
├── docker-compose.classifier.yml
├── install-classifier.sh
├── verify-no-secrets.sh
└── classifier/
    ├── classifier.py
    ├── taxonomy.yaml
    ├── Dockerfile
    └── requirements.txt
```

## Install on an existing Paperless-ngx server

Create an API token in Paperless: **My Profile → API Token**.

Clone the repo inside the existing Paperless directory, then copy the files into place:

```bash
cd ~/paperless
git clone https://github.com/svds12343/paperless-classifier.git classifier-backup
cp -a classifier-backup/. .
rm -rf classifier-backup
```

Create the local secrets file:

```bash
cp .classifier.env.example .classifier.env
nano .classifier.env
chmod 600 .classifier.env
```

Set at least:

```text
PAPERLESS_TOKEN=<new Paperless API token>
OPENAI_API_KEY=<OpenAI API key>
```

Then install/sync/start everything:

```bash
./install-classifier.sh
```

The installer builds the image, validates `taxonomy.yaml`, synchronizes classifier-managed tags, document types and storage paths, and starts the daemon.

## Disaster recovery

The runtime state is intentionally not stored in Git. On a fresh Paperless installation, clone this repository, create a new `.classifier.env`, and run `./install-classifier.sh`.

Because the default is:

```text
BOOTSTRAP_EXISTING=true
```

the classifier can bootstrap again against existing Paperless documents after a restore.

## Keeping the backup current

From a clone of this repository on the server:

```bash
./backup-config.sh ~/paperless
git diff
./verify-no-secrets.sh
```

Then commit and push the reviewed changes. `backup-config.sh` deliberately never copies `.classifier.env`, Paperless document data, API tokens, or runtime state.

## Security

Keep this repository **private**.

The following are deliberately excluded from Git:

- `.classifier.env`
- `docker-compose.env`
- Paperless data/media/consume/export directories
- classifier runtime state
- private keys and certificates
- API tokens and OpenAI keys

Before pushing changes, run:

```bash
./verify-no-secrets.sh
```

and still review the staged diff manually.

## Logs

```bash
cd ~/paperless
docker compose -f docker-compose.yml -f docker-compose.classifier.yml logs -f --tail=100 paperless-classifier
```

## Reclassify one document

```bash
docker compose -f docker-compose.yml -f docker-compose.classifier.yml run --rm \
  paperless-classifier python /app/classifier.py classify 1
```

## Process all unseen/changed documents once

```bash
docker compose -f docker-compose.yml -f docker-compose.classifier.yml run --rm \
  paperless-classifier python /app/classifier.py once
```

## After editing taxonomy.yaml

```bash
docker compose -f docker-compose.yml -f docker-compose.classifier.yml run --rm \
  paperless-classifier python /app/classifier.py sync
```

Then restart the daemon so the running process reloads the taxonomy:

```bash
docker compose -f docker-compose.yml -f docker-compose.classifier.yml restart paperless-classifier
```

Existing successfully classified documents are intentionally not overwritten just because taxonomy changed. Reclassify only the documents you want with the `classify ID` command.

## Safety properties

The model cannot create arbitrary tags or document types. Those values are schema enums derived from `taxonomy.yaml`; the daemon rejects anything outside them. Correspondents are the only taxonomy-like objects that may be created dynamically.

If classification confidence is under `MIN_CONFIDENCE` (default `0.84`) or the model explicitly considers the document ambiguous, metadata is not guessed: the document receives `AI::À vérifier`.

## Privacy

The service sends extracted document text to the configured OpenAI API. `store=false` is set on each Responses API request. Keep `.classifier.env` private (`chmod 600`).
