"""Score name redaction against eval/redaction_gold.yaml, layer by layer.

For each configuration (rules only, + house directory, + name detector, all) it reports:
- name recall: share of labelled names that no longer appear after redaction
- missed names, listed
- false alarms: words the notes need (NA, AA, weekdays...) that were removed, and name-free
  sentences that got a [NAME] tag
- time per sentence

The house directory is Harbourview's synthetic one; only some of the labelled names are in it, so the
detector's share of the work is visible.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import yaml

from axon.config import ROOT
from axon.redact import redact
from axon.tenants import get_tenant

GOLD = ROOT / "eval" / "redaction_gold.yaml"
REPORT = ROOT / "eval" / "REDACTION_REPORT.md"


@dataclass
class Score:
    name: str
    names: int = 0
    caught: int = 0
    missed: list[str] = field(default_factory=list)
    keep_lost: list[str] = field(default_factory=list)
    false_sentences: list[str] = field(default_factory=list)
    ms: float = 0.0

    @property
    def recall(self) -> float:
        return self.caught / self.names if self.names else 1.0


def _survives(word: str, text: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", text) is not None


def _name_words(name: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][a-z'\-]+", name)]  # initials ("J.") are not scored


def score(cases: list[dict], label: str, directory: tuple[str, ...], model: str | None) -> Score:
    s = Score(label)
    redact("warm up", directory=directory, model=model)  # model load time is not per-sentence time
    start = time.perf_counter()
    for c in cases:
        out = redact(c["text"], directory=directory, model=model).text
        for name in c.get("names", []):
            s.names += 1
            if any(_survives(w, out) for w in _name_words(name)):
                s.missed.append(f"{name} ({c['text']})")
            else:
                s.caught += 1
        s.keep_lost += [f"{k} ({c['text']})" for k in c.get("keep", []) if not _survives(k.split()[0], out)]
        if not c.get("names") and "[NAME]" in out:
            s.false_sentences.append(f"{c['text']} -> {out}")
    s.ms = (time.perf_counter() - start) * 1000 / len(cases)
    return s


def run(models: list[str]) -> list[Score]:
    cases = yaml.safe_load(GOLD.read_text())
    directory = get_tenant("harbourview").directory()
    configs = [("Rules only", (), None), ("Rules + house directory", directory, None)]
    for m in models:
        configs += [(f"Rules + detector ({m})", (), m), (f"Rules + directory + detector ({m})", directory, m)]
    return [score(cases, *c) for c in configs]


def report(scores: list[Score], n_cases: int) -> str:
    lines = [
        "# Name redaction: evaluation", "",
        f"{n_cases} labelled sentences (eval/redaction_gold.yaml): names with and without a relationship word, "
        "names in typed questions, and look-alikes that must survive (NA, AA, weekdays, places, organisations).", "",
        "| Layers | Names caught | Words wrongly removed | Name-free sentences tagged | ms per sentence |",
        "|---|---|---|---|---|",
    ]
    for s in scores:
        lines.append(f"| {s.name} | {s.caught}/{s.names} ({s.recall:.0%}) | {len(s.keep_lost)} | "
                     f"{len(s.false_sentences)} | {s.ms:.1f} |")
    for s in scores:
        if s.missed or s.keep_lost or s.false_sentences:
            lines += ["", f"## {s.name}", ""]
            lines += [f"- missed: {m}" for m in s.missed]
            lines += [f"- removed a needed word: {k}" for k in s.keep_lost]
            lines += [f"- tagged a name-free sentence: {f}" for f in s.false_sentences]
    return "\n".join(lines) + "\n"


def run_cli(models: list[str]) -> int:
    scores = run(models)
    text = report(scores, len(yaml.safe_load(GOLD.read_text())))
    REPORT.write_text(text)
    print(text)
    return 0
