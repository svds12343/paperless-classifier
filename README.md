# Paperless-ngx Strict AI Classifier

A Docker sidecar for Paperless-ngx that classifies documents with OpenAI while keeping all allowed document types, categories, tags and storage paths under strict control in `classifier/taxonomy.yaml`.

The included taxonomy is kept intact and works as the default configuration. Other users can edit it later if they want a different organization.

## What it does

- Automatically creates/synchronizes the document types, nested tags and storage paths defined in `classifier/taxonomy.yaml`.
- Polls Paperless after OCR; no Paperless workflow is required.
- Sends extracted OCR/text to OpenAI, not the original PDF.
- Uses strict structured output so the model can only choose codes present in the taxonomy.
- Validates the model output again before changing Paperless.
- Creates new correspondents when needed and reuses known/aliased correspondents.
- Preserves manual tags that are outside the classifier-managed taxonomy.
- Sets title, document type, tags, correspondent, date and storage path when reliable.
- Adds `AI::Classé`, `AI::À vérifier` or `AI::Erreur` status tags.
- Reprocesses documents if their extracted content changes.
- Can optionally classify documents that already existed before installation.

## Requirements

You need:

- an existing Paperless-ngx installation using Docker Compose;
- Docker with the `docker compose` command;
- a Paperless API token;
- an OpenAI API key;
- the OpenAI model you want the classifier to use.

The installer expects Paperless in `~/paperless` by default. Another location can be supplied explicitly.

## Installation

### 1. Create a Paperless API token

In Paperless, open **My Profile → API Token** and create/copy a token.

### 2. Clone this repository

The classifier stays in its own directory. Do not copy it into the Paperless directory.

```bash
cd ~
git clone https://github.com/svds12343/paperless-classifier.git
cd paperless-classifier
```

### 3. Configure everything before first start

Create your local configuration:

```bash
cp .classifier.env.example .classifier.env
nano .classifier.env
```

Review the entire file before starting the classifier. All supported configuration is set here from the start:

```text
# Paperless
PAPERLESS_URL=http://webserver:8000
PAPERLESS_TOKEN=your_paperless_api_token

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_REASONING_EFFORT=low

# Classification behaviour
POLL_INTERVAL=30
REQUEST_TIMEOUT=90
MAX_TEXT_CHARS=50000
MIN_CONFIDENCE=0.84
CORRESPONDENT_FUZZY_THRESHOLD=0.96
ERROR_RETRY_SECONDS=1800
BOOTSTRAP_EXISTING=true
TITLE_LANGUAGE=fr
LOG_LEVEL=INFO

# Internal paths
TAXONOMY_FILE=/app/taxonomy.yaml
STATE_FILE=/state/state.json
```

At minimum, replace the two credential placeholders with your real values. Also confirm every other value before the first start, especially `OPENAI_MODEL`, `BOOTSTRAP_EXISTING`, `TITLE_LANGUAGE` and `MIN_CONFIDENCE`.

What the settings control:

- `PAPERLESS_URL`: Paperless API address reachable from the classifier container.
- `PAPERLESS_TOKEN`: Paperless API token.
- `OPENAI_API_KEY`: OpenAI API key.
- `OPENAI_MODEL`: model sent to the OpenAI Responses API for every classification.
- `OPENAI_BASE_URL`: OpenAI-compatible API base URL.
- `OPENAI_REASONING_EFFORT`: reasoning effort requested from the model.
- `POLL_INTERVAL`: seconds between checks for documents.
- `REQUEST_TIMEOUT`: API request timeout in seconds.
- `MAX_TEXT_CHARS`: maximum OCR text sent for one document.
- `MIN_CONFIDENCE`: minimum accepted classification confidence.
- `CORRESPONDENT_FUZZY_THRESHOLD`: similarity required to reuse an existing correspondent.
- `ERROR_RETRY_SECONDS`: wait before retrying a technical failure.
- `BOOTSTRAP_EXISTING`: whether existing Paperless documents are processed on first startup.
- `TITLE_LANGUAGE`: language used for generated document titles.
- `LOG_LEVEL`: classifier logging level.
- `TAXONOMY_FILE`: taxonomy path inside the container.
- `STATE_FILE`: classifier state path inside the container.

Then protect the file:

```bash
chmod 600 .classifier.env
```

Do not start the classifier until this file is complete. The installer checks that every supported configuration key is present.

### 4. Install and start

If Paperless is in `~/paperless`:

```bash
./install-classifier.sh
```

If Paperless is somewhere else:

```bash
./install-classifier.sh /path/to/paperless
```

The installer will:

1. find the existing Paperless Compose file;
2. check that the complete classifier configuration exists;
3. build the classifier image;
4. validate `classifier/taxonomy.yaml`;
5. create/synchronize its tags, document types and storage paths in Paperless;
6. start the classifier sidecar.

It does not replace your Paperless configuration and does not copy classifier files into the Paperless directory.

## Check that it works

```bash
./classifierctl.sh status
./classifierctl.sh logs
```

Stop the live log view with `Ctrl+C`.

## Common commands

```bash
./classifierctl.sh status
./classifierctl.sh logs
./classifierctl.sh restart
./classifierctl.sh sync
./classifierctl.sh once
./classifierctl.sh classify 123
```

`classify 123` forces reclassification of Paperless document ID `123`.

If Paperless is not in `~/paperless`, either use:

```bash
PAPERLESS_DIR=/path/to/paperless ./classifierctl.sh logs
```

or:

```bash
./classifierctl.sh --paperless-dir /path/to/paperless logs
```

Run this for the full command list:

```bash
./classifierctl.sh help
```

## Taxonomy

The repository includes the full default taxonomy in:

```text
classifier/taxonomy.yaml
```

It defines:

- document types;
- top-level categories;
- nested tags;
- storage paths;
- classifier status tags;
- common correspondent aliases;
- classification rules.

The classifier cannot invent document-type, category or tag codes outside this file.

You do not need to change the taxonomy to start using the classifier.

If you edit it later, apply the changes with:

```bash
./classifierctl.sh sync
```

This validates the file, synchronizes it to Paperless and restarts the classifier.

Existing successfully classified documents are not automatically rewritten just because the taxonomy changed. Reclassify individual documents only when needed:

```bash
./classifierctl.sh classify DOCUMENT_ID
```

## Configuration

The complete runtime configuration lives in `.classifier.env` and must be reviewed during installation in step 3. There is no separate set of configuration that is intentionally deferred until later.

To change a setting after installation:

```bash
nano .classifier.env
./install-classifier.sh
```

`BOOTSTRAP_EXISTING=true` means documents already present in Paperless are eligible for classification on the classifier's first startup. Set it to `false` before that first startup if you only want newly added documents classified.

## Privacy

The classifier sends extracted document text to the configured OpenAI API. It does not upload the original PDF itself.

OpenAI requests use `store=false`.

Your secrets stay in `.classifier.env`, which is excluded from Git. Never commit this file.

## Updating the classifier

From the classifier directory:

```bash
git pull
./install-classifier.sh
```

This rebuilds and restarts the sidecar while keeping the local `.classifier.env` and classifier state.

## Backup / recovery

The important reusable configuration is already versioned in this repository, especially `classifier/taxonomy.yaml`.

Runtime state and credentials are intentionally not stored in Git.

After restoring Paperless on another server:

```bash
git clone https://github.com/svds12343/paperless-classifier.git
cd paperless-classifier
cp .classifier.env.example .classifier.env
nano .classifier.env
chmod 600 .classifier.env
./install-classifier.sh /path/to/paperless
```

Review the complete `.classifier.env` exactly as described in installation step 3 before running the installer.

With `BOOTSTRAP_EXISTING=true`, the classifier can classify the restored Paperless documents again.

## Security before publishing changes

Never commit:

- `.classifier.env`;
- Paperless API tokens;
- OpenAI API keys;
- Paperless document data;
- private keys or certificates;
- classifier runtime state.

Before pushing repository changes:

```bash
./verify-no-secrets.sh
```

## Repository layout

```text
paperless-classifier/
├── .classifier.env.example
├── .gitignore
├── README.md
├── classifierctl.sh
├── docker-compose.classifier.yml
├── install-classifier.sh
├── verify-no-secrets.sh
└── classifier/
    ├── classifier.py
    ├── taxonomy.yaml
    ├── Dockerfile
    └── requirements.txt
```
