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
- the OpenAI model you want the classifier to use;
- Paperless-ngx's own AI suggestions configured as the manual fallback for documents marked `AI::À vérifier`.

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

Review the entire file before starting the classifier. All supported classifier configuration is set here from the start:

```text
# Paperless
PAPERLESS_URL=http://webserver:8000
PAPERLESS_TOKEN=your_paperless_api_token

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.6-terra
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

Do not start the classifier until this file is complete. The installer checks that every supported classifier configuration key is present.

### 4. Configure Paperless-ngx AI suggestions

This is separate from the classifier configuration above. Paperless-ngx does not read the classifier's `.classifier.env`; its own AI backend must also be configured.

For the intended workflow of this project, Paperless AI suggestions should be enabled before you start using the classifier. The classifier can technically run without them, but you would lose the fast manual fallback for documents that it deliberately refuses to guess on.

With the OpenAI-compatible backend, configure Paperless with at least:

```text
PAPERLESS_AI_ENABLED=true
PAPERLESS_AI_LLM_BACKEND=openai-like
PAPERLESS_AI_LLM_MODEL=gpt-5.6-terra
PAPERLESS_AI_LLM_API_KEY=your_openai_api_key
PAPERLESS_AI_LLM_ENDPOINT=https://api.openai.com/v1
PAPERLESS_AI_LLM_OUTPUT_LANGUAGE=fr
```

You may reuse the same OpenAI API key as the classifier, or use a separate key if you want separate usage tracking.

Paperless-ngx also allows these settings to be configured from **Settings → Application Configuration**. Paperless's database configuration takes precedence over environment variables, so make sure you do not have an older conflicting value stored there.

An embedding backend / LLM index is not required just to use AI suggestions. It can be added later for RAG, similar-document retrieval and document chat.

#### Why this matters

The classifier is intentionally conservative. When confidence is too low or the document is ambiguous, it does not invent metadata; it marks the document:

```text
AI::À vérifier
```

When that happens:

1. open the document in Paperless-ngx;
2. click **✨ Suggest**;
3. let Paperless generate AI suggestions for the title, tags, correspondent, document type, storage path and date;
4. review the suggestions and accept the correct values.

This gives you an immediate second pass without manually filling every field. In practice, the Paperless suggestion is often enough to resolve a document the strict classifier sent for review because it can propose metadata interactively instead of being forced to satisfy the classifier's confidence threshold.

The **Suggest** action is still manual/opt-in: Paperless shows suggestions for you to review; it does not mean you should blindly accept every result.

After configuring Paperless AI, test it on one document before continuing. Open a document and confirm that **✨ Suggest** returns AI-generated metadata instead of an `Invalid AI configuration` error.

Paperless documentation: [AI features](https://docs.paperless-ngx.com/advanced_usage/#ai-features) and [AI configuration](https://docs.paperless-ngx.com/configuration/#ai).

### 5. Install and start the classifier

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

The complete classifier runtime configuration lives in `.classifier.env` and must be reviewed during installation in step 3. Paperless-ngx's own AI suggestion backend is configured separately in step 4; both should be configured before normal use.

To change a classifier setting after installation:

```bash
nano .classifier.env
./install-classifier.sh
```

`BOOTSTRAP_EXISTING=true` means documents already present in Paperless are eligible for classification on the classifier's first startup. Set it to `false` before that first startup if you only want newly added documents classified.

## Recommended model and API cost

The recommended default is:

```text
OPENAI_MODEL=gpt-5.6-terra
```

GPT-5.6 Terra is the best default for this classifier because it is designed to balance intelligence and cost. Document classification benefits from accurate interpretation of OCR text, document purpose, issuer, dates and taxonomy rules, so Terra gives more margin for difficult or ambiguous documents than choosing the cheapest model purely to minimize token cost.

If API cost is the main priority, `gpt-5.6-luna` is also compatible and is substantially cheaper. `gpt-5.6-sol` is the premium tier, but it is usually unnecessary for routine document classification.

Current standard OpenAI API text pricing, checked on 29 August 2026:

| Model | Input / 1M tokens | Output / 1M tokens | Suggested use |
| --- | ---: | ---: | --- |
| GPT-5.6 Luna | $0.20 | $1.20 | Lowest-cost/high-volume classification |
| **GPT-5.6 Terra** | **$2.00** | **$12.00** | **Recommended balance for this classifier** |
| GPT-5.6 Sol | $5.00 | $30.00 | Premium capability; usually overkill here |

For a personal Paperless archive, Terra is still fairly inexpensive. As an illustrative example, a classification using 10,000 input tokens and 300 output tokens would cost about **$0.0236** at standard Terra pricing:

```text
10,000 input tokens × $2 / 1,000,000   = $0.0200
   300 output tokens × $12 / 1,000,000 = $0.0036
                                         -------
                                         $0.0236
```

At that same illustrative usage, 100 documents would cost about **$2.36**, and 1,000 documents about **$23.60**. Many short documents can cost less; long OCR documents or larger model outputs can cost more. The classifier also caps document OCR text with `MAX_TEXT_CHARS` (50,000 by default), which prevents arbitrarily large document text from being sent in a single classification request.

Paperless-ngx AI suggestions use their own API calls, so clicking **✨ Suggest** also consumes tokens. Because it is only needed as a fallback for documents requiring review, the additional cost should normally remain small for a personal archive.

## Privacy

The classifier sends extracted document text to the configured OpenAI API. It does not upload the original PDF itself.

Paperless-ngx AI suggestions also send document content to the AI backend configured in Paperless. If you use OpenAI or another hosted provider for both, both features send document content outside your server and can incur API usage charges.

Classifier OpenAI requests use `store=false`.

Your classifier secrets stay in `.classifier.env`, which is excluded from Git. Never commit this file. Protect the Paperless AI API key with the same care.

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

Review the complete `.classifier.env` exactly as described in installation step 3 and reconfigure Paperless-ngx AI suggestions as described in step 4 before normal use.

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
