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

### 3. Configure Paperless and OpenAI

Create your local configuration:

```bash
cp .classifier.env.example .classifier.env
nano .classifier.env
```

Set or confirm these three values before starting the classifier:

```text
PAPERLESS_TOKEN=your_paperless_api_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
```

`OPENAI_MODEL` is the model that will be sent to the OpenAI Responses API for every classification request. Change it here if you want to use another compatible model.

The example configuration already contains `OPENAI_MODEL=gpt-5.4-mini`, but you should confirm that this is the model you want before the first start.

Then protect the file:

```bash
chmod 600 .classifier.env
```

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
2. build the classifier image;
3. validate `classifier/taxonomy.yaml`;
4. create/synchronize its tags, document types and storage paths in Paperless;
5. start the classifier sidecar.

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

The three core values to set or confirm during installation are:

```text
PAPERLESS_TOKEN=your_paperless_api_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
```

Other settings are optional tuning:

```text
PAPERLESS_URL=http://webserver:8000
MIN_CONFIDENCE=0.84
BOOTSTRAP_EXISTING=true
TITLE_LANGUAGE=fr
POLL_INTERVAL=30
LOG_LEVEL=INFO
```

`BOOTSTRAP_EXISTING=true` means documents already present in Paperless are eligible for classification after the classifier is installed for the first time.

Set it to `false` before first startup if you only want newly added documents classified.

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

Before running the installer, set `PAPERLESS_TOKEN`, `OPENAI_API_KEY` and confirm `OPENAI_MODEL` in `.classifier.env`.

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
