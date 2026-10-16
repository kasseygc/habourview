"""The one place that talks to a language model, with recorded replays for offline, deterministic runs (D-20).

Default: a self-hosted open model (Google Gemma 3 12B) served by Ollama on this machine. Nothing
leaves the computer. In production the same open model runs in Axon's own AWS account in Canada
(ca-central-1), so no outside company processes the text (D-21). A hosted-API client is kept only
to show the swap point; it is off unless explicitly chosen.

Modes (env AXON_LLM_MODE):
  auto    use a recording if one exists, otherwise call the model and save the answer
  replay  recordings only; fail if missing (what tests use)
  record  always call the model and overwrite the recording
  live    always call the model, save nothing

What is sent: instructions plus either the catalogue and a redacted question, or redacted notes.
Never resident records, query results, names, IDs or dates of birth.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from axon.config import ROOT

DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "gemma3:12b"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CASSETTE_DIR = ROOT / "eval" / "cassettes"


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class LLMCall:
    text: str
    model: str
    mode: str  # "replay" or "model"
    stop_reason: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None


def resolve_mode() -> str:
    mode = os.environ.get("AXON_LLM_MODE", "").strip() or "auto"
    if mode not in {"auto", "replay", "record", "live"}:
        raise ValueError(f"AXON_LLM_MODE must be auto, replay, record or live, not {mode!r}")
    return mode


def model_reachable(provider: str = DEFAULT_PROVIDER) -> bool:
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=1.5):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class SpecModel:
    def __init__(self, model: str | None = None, mode: str | None = None, provider: str | None = None,
                 cassette_dir: Path = CASSETTE_DIR, timeout_s: float = 600):
        self.provider = provider or os.environ.get("AXON_LLM_PROVIDER", DEFAULT_PROVIDER)
        self.model = model or os.environ.get("AXON_LLM_MODEL", DEFAULT_MODEL)
        self.mode = mode or resolve_mode()
        self.cassette_dir = cassette_dir
        self.timeout_s = timeout_s

    def warm_up(self) -> None:
        """Load the local model into memory so the first question doesn't pay for it."""
        if self.provider != "ollama" or not model_reachable(self.provider):
            return
        body = json.dumps({"model": self.model, "keep_alive": "60m"}).encode()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=120).read()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    def key(self, system: list[dict], user_text: str, schema: dict) -> str:
        payload = json.dumps(
            {"provider": self.provider, "model": self.model, "system": system, "user": user_text, "schema": schema},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:20]

    def complete(self, system: list[dict], user_text: str, schema: dict) -> LLMCall:
        key = self.key(system, user_text, schema)
        path = self.cassette_dir / f"{key}.json"
        if self.mode in {"auto", "replay"} and path.exists():
            rec = json.loads(path.read_text())
            return LLMCall(rec["response_text"], rec["model"], "replay", rec["stop_reason"],
                           rec.get("input_tokens"), rec.get("output_tokens"), rec.get("request_id"))
        if self.mode == "replay" or not model_reachable(self.provider):
            raise LLMUnavailable(
                "No recorded answer for this exact question, and the local model isn't running. "
                "Start it with `ollama serve` to ask new questions."
            )
        call = self._call_anthropic(system, user_text, schema) if self.provider == "anthropic" \
            else self._call_ollama(system, user_text, schema)
        if self.mode in {"auto", "record"}:
            self.cassette_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "key": key, "provider": self.provider, "model": call.model, "input_redacted": user_text,
                "response_text": call.text, "stop_reason": call.stop_reason,
                "input_tokens": call.input_tokens, "output_tokens": call.output_tokens,
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, indent=2, ensure_ascii=False) + "\n")
        return call

    def _call_ollama(self, system: list[dict], user_text: str, schema: dict) -> LLMCall:
        """Local open model. `format` constrains decoding to the JSON schema; temperature 0 for repeatability."""
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": "\n\n".join(b["text"] for b in system)},
                         {"role": "user", "content": user_text}],
            "format": schema,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0, "seed": 7, "num_ctx": 12288},
        }
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMUnavailable("The local model is busy or didn't answer in time. Try again in a moment.") from e
        return LLMCall(
            text=data["message"]["content"], model=data.get("model", self.model), mode="model",
            stop_reason=data.get("done_reason", "stop"),
            input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"),
        )

    def _call_anthropic(self, system: list[dict], user_text: str, schema: dict) -> LLMCall:
        """Optional hosted alternative (not used by default; would need agreements and Canadian residency)."""
        import anthropic

        response = anthropic.Anthropic().messages.create(
            model=self.model, max_tokens=16000, system=system,
            messages=[{"role": "user", "content": user_text}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "refusal":
            text = json.dumps({"action": "decline", "spec": None, "unclear_terms": [], "candidate_metrics": [],
                               "decline_reason": "unsafe"})
        else:
            text = next(b.text for b in response.content if b.type == "text")
        return LLMCall(text, response.model, "model", response.stop_reason,
                       response.usage.input_tokens, response.usage.output_tokens)
