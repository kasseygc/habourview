"""The one place that talks to Claude, with recorded replays for offline, deterministic runs (D-20).

Modes (env AXON_LLM_MODE):
  auto    use a recording if one exists, otherwise call the API (if a key is set) and save it
  replay  recordings only; fail if missing (what tests and CI use)
  record  always call the API and overwrite the recording
  live    always call the API, save nothing

What is sent: the system prompt (catalogue and house definitions) and the redacted question.
No resident records, query results or staff notes are ever sent.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from axon.config import ROOT

DEFAULT_MODEL = "claude-opus-5-5"
CASSETTE_DIR = ROOT / "eval" / "cassettes"


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class LLMCall:
    text: str
    model: str
    mode: str  # "replay" or "api"
    stop_reason: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None


def resolve_mode() -> str:
    mode = os.environ.get("AXON_LLM_MODE", "").strip() or "auto"
    if mode not in {"auto", "replay", "record", "live"}:
        raise ValueError(f"AXON_LLM_MODE must be auto, replay, record or live, not {mode!r}")
    return mode


def has_api_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class SpecModel:
    def __init__(self, model: str = DEFAULT_MODEL, mode: str | None = None, effort: str = "medium",
                 cassette_dir: Path = CASSETTE_DIR):
        self.model = model
        self.mode = mode or resolve_mode()
        self.effort = effort
        self.cassette_dir = cassette_dir

    def key(self, system: list[dict], user_text: str, schema: dict) -> str:
        payload = json.dumps(
            {"model": self.model, "effort": self.effort, "system": system, "user": user_text, "schema": schema},
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
        if self.mode == "replay" or not has_api_credentials():
            raise LLMUnavailable(
                "No recorded answer for this exact question, and no API key is set. "
                "Set ANTHROPIC_API_KEY to ask new questions."
            )
        call = self._call_api(system, user_text, schema)
        if self.mode in {"auto", "record"}:
            self.cassette_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "key": key,
                        "model": call.model,
                        "effort": self.effort,
                        "question_redacted": user_text,
                        "response_text": call.text,
                        "stop_reason": call.stop_reason,
                        "input_tokens": call.input_tokens,
                        "output_tokens": call.output_tokens,
                        "request_id": call.request_id,
                        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    },
                    indent=2,
                )
                + "\n"
            )
        return call

    def _call_api(self, system: list[dict], user_text: str, schema: dict) -> LLMCall:
        import anthropic

        client = anthropic.Anthropic()
        response = client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "refusal":
            text = json.dumps({"action": "decline", "spec": None, "unclear_terms": [], "candidate_metrics": [],
                               "decline_reason": "unsafe"})
        elif response.stop_reason == "max_tokens":
            raise LLMUnavailable("The model ran out of output space; try a shorter question.")
        else:
            text = next(b.text for b in response.content if b.type == "text")
        return LLMCall(
            text=text,
            model=response.model,
            mode="api",
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            request_id=getattr(response, "_request_id", None),
        )
