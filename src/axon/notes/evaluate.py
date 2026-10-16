"""Score note extraction against eval/notes_gold.yaml.

    uv run axon notes-eval                 # replay recorded model answers
    uv run axon notes-eval --mode record   # call the model and record

Precision, recall and F1 per field for rules alone, the model alone, and the combined result
(what the app shows). Recall matters most for risk flags. Also reports quotes the model invented
(rejected by the validator) and how much would go to staff review.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml

from axon.agent.llm import DEFAULT_MODEL, LLMUnavailable, SpecModel
from axon.config import ROOT
from axon.notes import model as notes_model
from axon.notes import rules
from axon.notes.schema import FIELDS
from axon.redact import redact

GOLD = ROOT / "eval" / "notes_gold.yaml"
REPORT = ROOT / "eval" / "NOTES_REPORT.md"


def load_gold(path: Path = GOLD) -> list[dict]:
    cases = yaml.safe_load(path.read_text())
    for i, c in enumerate(cases):
        c["id"] = f"g{i + 1:03d}"
        c["note"] = redact(c["note"]).text
        c["expect"] = {tuple(x.split(":")) for x in c["expect"]}
        c.setdefault("set", "file")
    return cases


def _prf(pairs: list[tuple[set, set]], field: str | None = None) -> dict:
    tp = fp = fn = 0
    for gold, pred in pairs:
        g = {x for x in gold if field is None or x[0] == field}
        p = {x for x in pred if field is None or x[0] == field}
        tp += len(g & p)
        fp += len(p - g)
        fn += len(g - p)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if tp + fp + fn else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def run(mode: str = "replay", model: str | None = None) -> dict:
    cases = load_gold()
    rule_pred = {c["id"]: {(f.field, f.value) for f in rules.extract(c["note"], c["status"])} for c in cases}
    items = [{"id": c["id"], "note": c["note"], "status": c["status"]} for c in cases if len(c["note"]) > 3]
    llm = SpecModel(model=model or DEFAULT_MODEL, mode=mode)
    try:
        out = notes_model.run(items, llm)
        model_pred = {c["id"]: {(f.field, f.value) for f in out.findings.get(c["id"], [])} for c in cases}
        rejected = out.rejected
    except LLMUnavailable:
        model_pred, rejected = None, []

    results: dict = {"model": llm.model, "mode": mode, "cases": len(cases),
                     "file_cases": sum(c["set"] == "file" for c in cases), "systems": {}}
    systems = {"rules": rule_pred}
    if model_pred is not None:
        systems["model"] = model_pred
        systems["rules + model"] = {k: rule_pred[k] | model_pred[k] for k in rule_pred}
    for name, pred in systems.items():
        per_set = {}
        for subset in ("file", "varied", None):
            pairs = [(c["expect"], pred[c["id"]]) for c in cases if subset is None or c["set"] == subset]
            per_set[subset or "all"] = {"overall": _prf(pairs), **{f: _prf(pairs, f) for f in FIELDS}}
        results["systems"][name] = per_set
    results["rejected_quotes"] = len(rejected)
    results["rejected_examples"] = rejected[:5]
    if model_pred is not None:
        disagree = sum(1 for c in cases if rule_pred[c["id"]] != model_pred[c["id"]])
        results["rules_model_disagree"] = disagree
    results["misses"] = defaultdict(list)
    for name, pred in systems.items():
        for c in cases:
            missed, extra = c["expect"] - pred[c["id"]], pred[c["id"]] - c["expect"]
            if missed or extra:
                results["misses"][name].append({"note": c["note"], "missed": sorted(missed), "extra": sorted(extra)})
    return results


def _pct(x) -> str:
    return "–" if x is None else f"{x:.0%}"


def write_report(r: dict) -> Path:
    lines = ["# Staff-note extraction: evaluation", "",
             f"{r['cases']} labelled notes ({r['file_cases']} from the Harbourview file, {r['cases'] - r['file_cases']} written in other words). "
             f"Model `{r['model']}`, mode `{r['mode']}`.", ""]
    if "model" not in r["systems"]:
        lines += ["Model answers are not recorded yet; only the rules are scored.", ""]
    lines += ["| System | Notes | Precision | Recall | F1 |", "|---|---|---|---|---|"]
    for name, sets in r["systems"].items():
        for subset in ("file", "varied", "all"):
            o = sets[subset]["overall"]
            lines.append(f"| {name} | {subset} | {_pct(o['precision'])} | {_pct(o['recall'])} | {_pct(o['f1'])} |")
    lines += ["", "Recall by field, all notes:", "", "| System | " + " | ".join(FIELDS) + " |",
              "|---|" + "---|" * len(FIELDS)]
    for name, sets in r["systems"].items():
        lines.append(f"| {name} | " + " | ".join(_pct(sets["all"][f]["recall"]) for f in FIELDS) + " |")
    lines += ["", f"Quotes not found in the note (rejected by the validator): {r['rejected_quotes']}"]
    if "rules_model_disagree" in r:
        lines.append(f"Notes where rules and model disagree (sent to review): {r['rules_model_disagree']}")
    for name, misses in r["misses"].items():
        lines += ["", f"## Misses: {name}", ""]
        lines += [f"- “{m['note']}”: missed {', '.join(':'.join(x) for x in m['missed']) or 'nothing'}; "
                  f"extra {', '.join(':'.join(x) for x in m['extra']) or 'nothing'}" for m in misses] or ["- none"]
    REPORT.write_text("\n".join(lines) + "\n")
    return REPORT


def run_cli(mode: str, model: str | None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    r = run(mode, model)
    (ROOT / "eval" / "notes_results.json").write_text(json.dumps(r, indent=2, default=str) + "\n")
    print(write_report(r).read_text().split("## Misses")[0])
    return 0
