#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import logging
import os
import re
import signal
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

LOG = logging.getLogger("paperless-classifier")
STOP = False


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Config:
    paperless_url: str
    paperless_token: str
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    reasoning_effort: str
    poll_interval: int
    request_timeout: int
    max_text_chars: int
    min_confidence: float
    fuzzy_threshold: float
    error_retry_seconds: int
    bootstrap_existing: bool
    title_language: str
    taxonomy_file: str
    state_file: str
    log_level: str

    @classmethod
    def load(cls, require_openai: bool = True) -> "Config":
        pt = os.getenv("PAPERLESS_TOKEN", "").strip()
        ok = os.getenv("OPENAI_API_KEY", "").strip()
        if not pt:
            raise RuntimeError("PAPERLESS_TOKEN is required")
        if require_openai and not ok:
            raise RuntimeError("OPENAI_API_KEY is required")
        return cls(
            paperless_url=os.getenv("PAPERLESS_URL", "http://webserver:8000").rstrip("/"),
            paperless_token=pt,
            openai_api_key=ok,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "low"),
            poll_interval=env_int("POLL_INTERVAL", 30),
            request_timeout=env_int("REQUEST_TIMEOUT", 90),
            max_text_chars=env_int("MAX_TEXT_CHARS", 50000),
            min_confidence=env_float("MIN_CONFIDENCE", 0.84),
            fuzzy_threshold=env_float("CORRESPONDENT_FUZZY_THRESHOLD", 0.96),
            error_retry_seconds=env_int("ERROR_RETRY_SECONDS", 1800),
            bootstrap_existing=env_bool("BOOTSTRAP_EXISTING", True),
            title_language=os.getenv("TITLE_LANGUAGE", "fr"),
            taxonomy_file=os.getenv("TAXONOMY_FILE", "/app/taxonomy.yaml"),
            state_file=os.getenv("STATE_FILE", "/state/state.json"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


class State:
    def __init__(self, path: str):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {"documents": {}, "initialized": False}
        self.data.setdefault("documents", {})
        self.data.setdefault("initialized", False)

    def get(self, doc_id: int) -> dict[str, Any]:
        return self.data["documents"].get(str(doc_id), {})

    def set(self, doc_id: int, **values: Any) -> None:
        current = dict(self.get(doc_id))
        current.update(values)
        self.data["documents"][str(doc_id)] = current
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)


def retry_request(session: requests.Session, method: str, url: str, *, timeout: int, attempts: int = 4, **kwargs: Any) -> requests.Response:
    retry_status = {408, 425, 429, 500, 502, 503, 504}
    for n in range(1, attempts + 1):
        try:
            r = session.request(method, url, timeout=timeout, **kwargs)
            if r.status_code not in retry_status or n == attempts:
                return r
            delay = min(2 ** (n - 1), 12)
            if r.headers.get("Retry-After", "").isdigit():
                delay = min(int(r.headers["Retry-After"]), 60)
            LOG.warning("HTTP %s from %s; retrying in %ss", r.status_code, url, delay)
            time.sleep(delay)
        except (requests.ConnectionError, requests.Timeout):
            if n == attempts:
                raise
            time.sleep(min(2 ** (n - 1), 12))
    raise RuntimeError("request retry loop failed")


class Paperless:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = cfg.paperless_url + "/api"
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Token {cfg.paperless_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "paperless-strict-classifier/1.0",
        })

    def request(self, method: str, path: str, *, params=None, body=None, expected=(200,)) -> Any:
        r = retry_request(self.s, method, self.base + "/" + path.lstrip("/"), timeout=self.cfg.request_timeout, params=params, json=body)
        if r.status_code not in expected:
            raise RuntimeError(f"Paperless {method} {path}: HTTP {r.status_code}: {r.text[:1500]}")
        return r.json() if r.content else None

    def list_all(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("page_size", 100)
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            params["page"] = page
            payload = self.request("GET", f"{endpoint}/", params=params)
            if isinstance(payload, list):
                return payload
            batch = payload.get("results", [])
            out.extend(batch)
            if not batch or len(out) >= int(payload.get("count", len(out))):
                return out
            page += 1

    def get_document(self, doc_id: int) -> dict[str, Any]:
        return self.request("GET", f"documents/{doc_id}/")

    def patch_document(self, doc_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", f"documents/{doc_id}/", body=body)

    def add_note(self, doc_id: int, text: str) -> None:
        try:
            self.request("POST", f"documents/{doc_id}/notes/", body={"note": text[:3500]}, expected=(200, 201))
        except Exception as e:
            LOG.warning("Could not add note to document %s: %s", doc_id, e)

    def ensure_object(self, endpoint: str, name: str, desired: dict[str, Any]) -> dict[str, Any]:
        objects = self.list_all(endpoint)
        existing = next((x for x in objects if str(x.get("name", "")).casefold() == name.casefold()), None)
        body = {"name": name, **desired}
        if not existing:
            return self.request("POST", f"{endpoint}/", body=body, expected=(201,))
        # Keep classifier-owned objects deterministic. Patch only known writable fields.
        patch = {k: v for k, v in body.items() if existing.get(k) != v}
        if patch:
            try:
                return self.request("PATCH", f"{endpoint}/{existing['id']}/", body=patch)
            except Exception as e:
                LOG.warning("Could not fully sync existing %s %r: %s", endpoint, name, e)
        return existing

    def ensure_tag(self, name: str, *, color: str, parent: int | None = None) -> dict[str, Any]:
        return self.ensure_object("tags", name, {
            "color": color,
            "match": "",
            "matching_algorithm": 0,
            "is_insensitive": True,
            "is_inbox_tag": False,
            "parent": parent,
        })

    def ensure_document_type(self, name: str) -> dict[str, Any]:
        return self.ensure_object("document_types", name, {
            "match": "", "matching_algorithm": 0, "is_insensitive": True,
        })

    def ensure_storage_path(self, name: str, path: str) -> dict[str, Any]:
        return self.ensure_object("storage_paths", name, {
            "path": path, "match": "", "matching_algorithm": 0, "is_insensitive": True,
        })

    def ensure_correspondent(self, name: str) -> dict[str, Any]:
        return self.ensure_object("correspondents", name, {
            "match": "", "matching_algorithm": 0, "is_insensitive": True,
        })


class Taxonomy:
    def __init__(self, path: str):
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError("taxonomy.yaml is invalid")
        self.document_types: dict[str, dict[str, Any]] = raw["document_types"]
        self.categories: dict[str, dict[str, Any]] = raw["categories"]
        self.status_tags: dict[str, dict[str, Any]] = raw["status_tags"]
        self.aliases: dict[str, list[str]] = raw.get("correspondent_aliases", {})
        self.rules: list[str] = raw.get("rules", [])
        self.validate()

    def validate(self) -> None:
        if not self.document_types or not self.categories:
            raise RuntimeError("taxonomy requires document_types and categories")
        all_codes: set[str] = set()
        for code in self.document_types:
            if not re.fullmatch(r"[a-z0-9_]+", code):
                raise RuntimeError(f"invalid document type code {code}")
        for cat_code, cat in self.categories.items():
            if not re.fullmatch(r"[a-z0-9_]+", cat_code) or not cat.get("tags") or not cat.get("storage_path"):
                raise RuntimeError(f"invalid category {cat_code}")
            for tag_code in cat["tags"]:
                full = f"{cat_code}.{tag_code}"
                if full in all_codes:
                    raise RuntimeError(f"duplicate tag code {full}")
                all_codes.add(full)
        for status in ("classified", "review", "error"):
            if status not in self.status_tags:
                raise RuntimeError(f"missing status tag {status}")

    @property
    def type_codes(self) -> list[str]:
        return list(self.document_types)

    @property
    def category_codes(self) -> list[str]:
        return list(self.categories)

    @property
    def leaf_codes(self) -> list[str]:
        return [f"{c}.{t}" for c, cat in self.categories.items() for t in cat["tags"]]


@dataclass
class Synced:
    types: dict[str, int]
    category_tags: dict[str, int]
    leaves: dict[str, int]
    paths: dict[str, int]
    statuses: dict[str, int]
    managed_tag_ids: set[int]
    leaf_category: dict[str, str]


def sync_taxonomy(api: Paperless, tax: Taxonomy) -> Synced:
    types: dict[str, int] = {}
    cats: dict[str, int] = {}
    leaves: dict[str, int] = {}
    paths: dict[str, int] = {}
    statuses: dict[str, int] = {}
    managed: set[int] = set()
    leaf_category: dict[str, str] = {}

    for code, item in tax.document_types.items():
        types[code] = int(api.ensure_document_type(item["name"])["id"])

    for ccode, cat in tax.categories.items():
        parent = api.ensure_tag(cat["name"], color=cat.get("color", "#cccccc"))
        parent_id = int(parent["id"])
        cats[ccode] = parent_id
        managed.add(parent_id)
        for tcode, item in cat["tags"].items():
            obj = api.ensure_tag(item["name"], color=item.get("color", cat.get("color", "#cccccc")), parent=parent_id)
            full = f"{ccode}.{tcode}"
            leaves[full] = int(obj["id"])
            leaf_category[full] = ccode
            managed.add(int(obj["id"]))
        paths[ccode] = int(api.ensure_storage_path(cat["name"], cat["storage_path"])["id"])

    for code, item in tax.status_tags.items():
        obj = api.ensure_tag(item["name"], color=item.get("color", "#cccccc"))
        statuses[code] = int(obj["id"])

    LOG.info("Taxonomy synced: %d types, %d categories, %d leaf tags", len(types), len(cats), len(leaves))
    return Synced(types, cats, leaves, paths, statuses, managed, leaf_category)


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^\w\s]", " ", value.casefold())
    suffixes = {"ag", "sa", "sarl", "gmbh", "ltd", "limited", "inc", "corp", "llc", "plc"}
    return " ".join(x for x in value.split() if x not in suffixes)


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" \t-–—:;,")
    if value.casefold() in {"", "none", "unknown", "inconnu", "aucun", "aucune", "n/a", "na"}:
        return ""
    return value[:128].rstrip()


def resolve_correspondent(api: Paperless, tax: Taxonomy, proposed: str, threshold: float) -> int | None:
    proposed = clean_name(proposed)
    if not proposed:
        return None

    aliases: dict[str, str] = {}
    for canonical, vals in tax.aliases.items():
        aliases[normalize_name(canonical)] = canonical
        for val in vals:
            aliases[normalize_name(val)] = canonical
    canonical = aliases.get(normalize_name(proposed), proposed)
    target = normalize_name(canonical)

    existing = api.list_all("correspondents")
    for item in existing:
        if normalize_name(str(item.get("name", ""))) == target:
            return int(item["id"])

    best_score = 0.0
    best = None
    for item in existing:
        norm = normalize_name(str(item.get("name", "")))
        if not norm:
            continue
        score = difflib.SequenceMatcher(a=target, b=norm).ratio()
        if score > best_score:
            best_score, best = score, item
    if best is not None and best_score >= threshold:
        LOG.info("Reusing correspondent %r for %r (%.3f)", best["name"], canonical, best_score)
        return int(best["id"])

    created = api.ensure_correspondent(canonical)
    LOG.info("Created correspondent %s", created["name"])
    return int(created["id"])


def build_schema(tax: Taxonomy) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "issuer": {"type": "string"},
            "created_date": {"type": "string"},
            "document_type": {"type": "string", "enum": tax.type_codes},
            "primary_category": {"type": "string", "enum": tax.category_codes},
            "tags": {"type": "array", "items": {"type": "string", "enum": tax.leaf_codes}, "minItems": 1, "maxItems": 5},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "review_required": {"type": "boolean"},
            "review_reason": {"type": "string"},
        },
        "required": ["title", "issuer", "created_date", "document_type", "primary_category", "tags", "confidence", "review_required", "review_reason"],
        "additionalProperties": False,
    }


def taxonomy_text(tax: Taxonomy) -> tuple[str, str, str]:
    types = "\n".join(f"- {c}: {x['name']} — {x.get('description','')}" for c, x in tax.document_types.items())
    tags: list[str] = []
    for c, cat in tax.categories.items():
        tags.append(f"- {c}: {cat['name']} — {cat.get('description','')}")
        for t, item in cat["tags"].items():
            tags.append(f"  - {c}.{t}: {item['name']} — {item.get('description','')}")
    rules = "\n".join(f"- {r}" for r in tax.rules)
    return types, "\n".join(tags), rules


def extract_output_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                return str(part.get("text", ""))
            if part.get("type") == "refusal":
                raise RuntimeError("OpenAI refused classification")
    raise RuntimeError("OpenAI returned no output_text")


def call_openai(cfg: Config, api: Paperless, tax: Taxonomy, doc: dict[str, Any]) -> dict[str, Any]:
    content = str(doc.get("content") or "").strip()
    if len(content) < 20:
        raise ValueError("OCR/extracted text is empty or too short")
    if len(content) > cfg.max_text_chars:
        head = int(cfg.max_text_chars * 0.75)
        content = content[:head] + "\n\n[...TRUNCATED...]\n\n" + content[-(cfg.max_text_chars - head):]

    types, tags, rules = taxonomy_text(tax)
    known = api.list_all("correspondents")
    known_text = "\n".join(f"- {x['name']}" for x in known[:500]) or "- none"

    system = f"""You are the strict metadata classifier for a Paperless-ngx archive.

Hard constraints:
- The JSON schema is authoritative. Never invent codes.
- Choose exactly one document_type and one primary_category.
- Choose 1 to 5 useful leaf tags; at least one must belong to primary_category.
- issuer is the actual sender/issuer, never the recipient.
- If issuer clearly matches a known correspondent, copy that known name exactly.
- For a genuinely new issuer, return a stable clean organization/person name only: no address, department routing label, account/invoice/case number or document-specific suffix.
- If no issuer can be identified reliably, issuer must be an empty string.
- created_date is the document issue/signing/transaction date in YYYY-MM-DD; empty if uncertain.
- Generate a concise useful title in {cfg.title_language}.
- confidence measures the classification as a whole.
- review_required MUST be true if OCR is poor, the issuer/type/category is ambiguous, or you would otherwise guess.
- review_reason is empty when review_required=false; otherwise give one concise reason.

Organization rules:
{rules}

Document types:
{types}

Categories and leaf tags:
{tags}

Existing correspondents:
{known_text}
"""

    body: dict[str, Any] = {
        "model": cfg.openai_model,
        "store": False,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Classify this OCR text:\n\n" + content},
        ],
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "paperless_classification",
                "strict": True,
                "schema": build_schema(tax),
            },
        },
        "max_output_tokens": 1000,
    }
    if cfg.reasoning_effort:
        body["reasoning"] = {"effort": cfg.reasoning_effort}

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {cfg.openai_api_key}", "Content-Type": "application/json"})
    r = retry_request(s, "POST", cfg.openai_base_url + "/responses", timeout=cfg.request_timeout, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI HTTP {r.status_code}: {r.text[:1500]}")
    payload = r.json()
    if payload.get("status") not in (None, "completed"):
        raise RuntimeError(f"OpenAI response status {payload.get('status')}: {payload.get('error')}")
    result = json.loads(extract_output_text(payload))
    usage = payload.get("usage") or {}
    LOG.info("OpenAI usage: input=%s output=%s", usage.get("input_tokens", "?"), usage.get("output_tokens", "?"))
    return result


def validate_result(result: dict[str, Any], synced: Synced, minimum: float) -> tuple[bool, str]:
    try:
        if result["document_type"] not in synced.types:
            return False, "invalid document type"
        if result["primary_category"] not in synced.paths:
            return False, "invalid primary category"
        tags = result["tags"]
        if not isinstance(tags, list) or not 1 <= len(tags) <= 5 or len(tags) != len(set(tags)):
            return False, "invalid tag list"
        if any(t not in synced.leaves for t in tags):
            return False, "unknown tag"
        if not any(synced.leaf_category[t] == result["primary_category"] for t in tags):
            return False, "no selected tag belongs to primary category"
        if bool(result["review_required"]):
            return False, str(result.get("review_reason") or "model requested review")
        confidence = float(result["confidence"])
        if confidence < minimum:
            return False, f"confidence {confidence:.2f} below {minimum:.2f}"
    except (KeyError, TypeError, ValueError) as e:
        return False, f"invalid structured result: {e}"
    return True, ""


def parse_date(value: str) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        d = dt.date.fromisoformat(value)
        if 1900 <= d.year <= 2100:
            return d.isoformat()
    except ValueError:
        pass
    return None


def fingerprint(doc: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(str(doc.get("content") or "").encode("utf-8", "ignore"))
    h.update(b"\0")
    h.update(str(doc.get("original_file_name") or doc.get("original_filename") or "").encode("utf-8", "ignore"))
    return h.hexdigest()


def status_tags(doc: dict[str, Any], synced: Synced, status: str) -> list[int]:
    tags = set(int(x) for x in doc.get("tags", []))
    tags -= set(synced.statuses.values())
    tags.add(synced.statuses[status])
    return sorted(tags)


def mark_status(api: Paperless, doc: dict[str, Any], synced: Synced, status: str, note: str) -> None:
    api.patch_document(int(doc["id"]), {"tags": status_tags(doc, synced, status)})
    api.add_note(int(doc["id"]), note)


def apply_result(cfg: Config, api: Paperless, tax: Taxonomy, synced: Synced, doc: dict[str, Any], result: dict[str, Any]) -> None:
    tags = set(int(x) for x in doc.get("tags", []))
    tags -= synced.managed_tag_ids
    tags -= set(synced.statuses.values())
    tags |= {synced.leaves[t] for t in result["tags"]}
    tags.add(synced.statuses["classified"])

    payload: dict[str, Any] = {
        "title": clean_name(result.get("title", "")) or str(doc.get("title") or f"Document {doc['id']}")[:128],
        "document_type": synced.types[result["document_type"]],
        "storage_path": synced.paths[result["primary_category"]],
        "tags": sorted(tags),
    }

    issuer = clean_name(result.get("issuer", ""))
    if issuer:
        correspondent_id = resolve_correspondent(api, tax, issuer, cfg.fuzzy_threshold)
        if correspondent_id is not None:
            payload["correspondent"] = correspondent_id

    created = parse_date(result.get("created_date", ""))
    if created:
        payload["created"] = created

    api.patch_document(int(doc["id"]), payload)


def classify_document(cfg: Config, api: Paperless, tax: Taxonomy, synced: Synced, state: State, doc_id: int, *, force: bool = False) -> None:
    doc = api.get_document(doc_id)
    fp = fingerprint(doc)
    record = state.get(doc_id)
    now = time.time()

    if not force and record.get("fingerprint") == fp:
        if record.get("status") in {"classified", "review", "ignored_existing"}:
            return
        if record.get("status") == "error" and now < float(record.get("retry_after", 0)):
            return

    try:
        result = call_openai(cfg, api, tax, doc)
        valid, reason = validate_result(result, synced, cfg.min_confidence)
        if not valid:
            mark_status(api, doc, synced, "review", f"AI classifier — review required: {reason}")
            state.set(doc_id, fingerprint=fp, status="review", reason=reason, at=dt.datetime.now(dt.timezone.utc).isoformat())
            LOG.warning("Document %s -> review: %s", doc_id, reason)
            return

        apply_result(cfg, api, tax, synced, doc, result)
        state.set(doc_id, fingerprint=fp, status="classified", confidence=float(result["confidence"]), at=dt.datetime.now(dt.timezone.utc).isoformat())
        LOG.info("Document %s classified: %s / %s / %s", doc_id, result["document_type"], result["primary_category"], ",".join(result["tags"]))
    except ValueError as e:
        mark_status(api, doc, synced, "review", f"AI classifier — review required: {e}")
        state.set(doc_id, fingerprint=fp, status="review", reason=str(e), at=dt.datetime.now(dt.timezone.utc).isoformat())
    except Exception as e:
        LOG.exception("Classification error for document %s", doc_id)
        try:
            fresh = api.get_document(doc_id)
            mark_status(api, fresh, synced, "error", f"AI classifier — transient/error: {str(e)[:1000]}")
        except Exception:
            pass
        state.set(doc_id, fingerprint=fp, status="error", reason=str(e)[:1000], retry_after=now + cfg.error_retry_seconds, at=dt.datetime.now(dt.timezone.utc).isoformat())


def process_cycle(cfg: Config, api: Paperless, tax: Taxonomy, synced: Synced, state: State) -> int:
    docs = api.list_all("documents", {"ordering": "id"})
    count = 0
    for summary in docs:
        if STOP:
            break
        doc_id = int(summary["id"])
        full = api.get_document(doc_id)
        fp = fingerprint(full)
        rec = state.get(doc_id)
        if rec.get("fingerprint") == fp and rec.get("status") in {"classified", "review", "ignored_existing"}:
            continue
        if rec.get("fingerprint") == fp and rec.get("status") == "error" and time.time() < float(rec.get("retry_after", 0)):
            continue
        classify_document(cfg, api, tax, synced, state, doc_id)
        count += 1
    return count


def signal_stop(*_: Any) -> None:
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict OpenAI classifier for Paperless-ngx")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("daemon", "once", "sync", "validate", "health", "reset-state"):
        sub.add_parser(name)
    one = sub.add_parser("classify")
    one.add_argument("document_id", type=int)
    args = parser.parse_args()

    require_openai = args.cmd in {"daemon", "once", "classify"}
    cfg = Config.load(require_openai=require_openai)
    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    tax = Taxonomy(cfg.taxonomy_file)

    if args.cmd == "validate":
        LOG.info("Taxonomy valid: %d types, %d categories, %d leaf tags", len(tax.document_types), len(tax.categories), len(tax.leaf_codes))
        return 0

    api = Paperless(cfg)
    if args.cmd == "health":
        api.list_all("documents", {"page_size": 1})
        return 0

    synced = sync_taxonomy(api, tax)
    if args.cmd == "sync":
        return 0

    state = State(cfg.state_file)
    if args.cmd == "reset-state":
        state.data = {"documents": {}, "initialized": True}
        state.save()
        return 0

    if not state.data.get("initialized"):
        if not cfg.bootstrap_existing:
            for summary in api.list_all("documents", {"ordering": "id"}):
                full = api.get_document(int(summary["id"]))
                state.set(int(summary["id"]), fingerprint=fingerprint(full), status="ignored_existing")
        state.data["initialized"] = True
        state.save()

    if args.cmd == "classify":
        classify_document(cfg, api, tax, synced, state, args.document_id, force=True)
        return 0

    if args.cmd == "once":
        process_cycle(cfg, api, tax, synced, state)
        return 0

    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    LOG.info("Daemon started: model=%s poll=%ss confidence>=%.2f", cfg.openai_model, cfg.poll_interval, cfg.min_confidence)
    while not STOP:
        try:
            process_cycle(cfg, api, tax, synced, state)
        except Exception:
            LOG.exception("Polling cycle failed")
        for _ in range(cfg.poll_interval):
            if STOP:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
