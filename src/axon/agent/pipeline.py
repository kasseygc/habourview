"""Question -> redact -> clarify? -> LLM spec -> validate -> compile -> guard -> run -> answer.

The tenant comes only from the Session. Every outcome, including declines and failures,
is written to the audit log.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from axon.agent import glossary
from axon.agent.audit import AuditLog
from axon.agent.compiler import compile_spec
from axon.agent.definitions import GENERIC_PREFIX, Definition, DefinitionStore, choice_for
from axon.agent.executor import QueryTimeout, run_query
from axon.agent.glossary import GLOSSARY, Choice
from axon.agent.guard import UnsafeQuery, check_sql
from axon.agent.llm import LLMUnavailable, SpecModel
from axon.agent.narrate import narrate, small_cell_note
from axon.agent.prompt import system_blocks
from axon.agent.registry import METRICS
from axon.agent.spec import ExecutedSpec, QuerySpec, SpecError, apply_patch, llm_json_schema, parse_reply
from axon.config import AS_OF
from axon.redact import redact
from axon.tenants import get_tenant

ROW_LEVEL = re.compile(
    r"^\s*who\b|\bwhich (?:residents?|clients?|people|person|youth)\b|\b(?:list|show|give)(?: me)? (?:the |all )?"
    r"(?:names?|residents|clients|people)\b|\bnames? of\b",
    re.IGNORECASE,
)
IDENTIFIER_TAGS = {"NAME", "RESIDENT_ID", "PHONE", "EMAIL", "HEALTH_CARD", "SIN"}

# Every AI-assisted output says so (as Axon does for every AI-assisted report).
AI_DISCLOSURE = ("AI-assisted: a self-hosted language model turned your question into a query. It never saw "
                 "resident records, and every number comes from the executed query. Review before sharing.")

DECLINE_MESSAGES = {
    "row_level": "I can only give totals, not information about individual people. "
                 "For a specific person, open their case file, which has its own access controls.",
    "write_request": "I can only read data. Changes to records are made in the case-management screens.",
    "other_house": "I can only answer questions about your own house.",
    "out_of_scope": "That isn't something I can answer yet.",
    "unsafe": "I can't help with that request.",
}


@dataclass(frozen=True)
class Session:
    tenant_id: str
    user_id: str
    role: str = "director"


@dataclass
class Clarification:
    term: str
    question: str
    why: str
    choices: list[Choice]
    event_id: str | None = None
    kind: str = "clarify"


@dataclass
class Declined:
    reason: str
    message: str
    event_id: str | None = None
    kind: str = "decline"


@dataclass
class Failed:
    message: str
    event_id: str | None = None
    kind: str = "failed"


@dataclass
class Answer:
    executed: ExecutedSpec
    sql: str
    params: list
    frame: pd.DataFrame
    text: str
    caveats: list[str] = field(default_factory=list)
    definitions: list[Definition] = field(default_factory=list)
    truncated: bool = False
    elapsed_ms: int = 0
    llm_mode: str = ""
    event_id: str | None = None
    disclosure: str = AI_DISCLOSURE
    kind: str = "answer"

    @property
    def spec(self) -> QuerySpec:
        return self.executed.spec


Result = Answer | Clarification | Declined | Failed


def supported_questions() -> str:
    return "I can answer questions about: " + "; ".join(m.label.lower() for m in METRICS.values()) + "."


class Agent:
    def __init__(self, llm: SpecModel | None = None, store: DefinitionStore | None = None, audit: AuditLog | None = None):
        self.llm = llm or SpecModel()
        self.store = store or DefinitionStore()
        self.audit = audit or AuditLog()

    def ask(self, question: str, session: Session) -> Result:
        started = time.perf_counter()
        tenant = get_tenant(session.tenant_id)
        red = redact(question, keep_dates=True)
        log = dict(tenant=tenant.id, user=session.user_id, role=session.role, question_redacted=red.text,
                   redacted_types=sorted(set(red.found)))

        def done(result: Result, **extra) -> Result:
            result.event_id = self.audit.write(
                **log, outcome=result.kind, elapsed_ms=int((time.perf_counter() - started) * 1000), **extra
            )
            return result

        # 1. Questions about a person never reach the model.
        if IDENTIFIER_TAGS & set(red.found) or ROW_LEVEL.search(red.text):
            return done(Declined("row_level", DECLINE_MESSAGES["row_level"]), decided_by="rules")

        # 2. Known fuzzy words must be defined for this house before anything runs.
        definitions = self.store.current(tenant.id)
        terms = glossary.find_terms(red.text)
        for term in terms:
            if term not in definitions:
                t = GLOSSARY[term]
                return done(Clarification(term, t.question, t.why, list(t.choices)), term=term, decided_by="rules")

        # 3. The model proposes a spec (or asks, or declines). One retry on an invalid spec.
        schema = llm_json_schema()
        # Only the definitions for words in this question: a shorter prompt, and stable recordings.
        system = system_blocks({t: d for t, d in definitions.items() if t in terms})
        user_text = red.text
        reply = None
        error = None
        llm_mode = ""
        for attempt in range(2):
            try:
                call = self.llm.complete(system, user_text, schema)
            except LLMUnavailable as e:
                return done(Failed(str(e)), error="llm_unavailable")
            llm_mode = call.mode
            log.update(model=call.model, llm_mode=call.mode, input_tokens=call.input_tokens,
                       output_tokens=call.output_tokens)
            try:
                reply = parse_reply(call.text)
                break
            except SpecError as e:
                error = str(e)
                user_text = (f"{red.text}\n\n(A previous reply was rejected by the validator: {error[:400]}. "
                             "Reply again, using only catalogue ids allowed for the chosen metric.)")
        if reply is None:
            return done(Failed("I couldn't turn that into a supported question. " + supported_questions()),
                        error=f"invalid_spec: {error}")

        if reply.action == "decline":
            reason = reply.decline_reason or "out_of_scope"
            message = DECLINE_MESSAGES[reason] + (" " + supported_questions() if reason == "out_of_scope" else "")
            return done(Declined(reason, message), decided_by="model")

        if reply.action == "clarify":
            term = reply.unclear_terms[0]
            if term in GLOSSARY:
                t = GLOSSARY[term]
                return done(Clarification(term, t.question, t.why, list(t.choices)), term=term, decided_by="model")
            choices = [choice_for(term, f"{GENERIC_PREFIX}{m}") for m in reply.candidate_metrics[:4]]
            if not choices:
                return done(Declined("out_of_scope", DECLINE_MESSAGES["out_of_scope"] + " " + supported_questions()),
                            decided_by="model")
            return done(
                Clarification(term, f"What do you mean by '{term}'?",
                              "That word could match more than one measure.", choices),
                term=term, decided_by="model",
            )

        # 4. Apply this house's definitions for the words used, deterministically.
        spec = reply.spec
        used: list[Definition] = []
        try:
            for term in terms:
                d = definitions[term]
                spec = apply_patch(spec, choice_for(term, d.choice_id).patch)
                used.append(d)
        except (ValueError, KeyError) as e:
            return done(Failed("A saved house definition doesn't fit this question. " + str(e)[:200]),
                        error="definition_conflict")
        executed = ExecutedSpec(spec=spec, definitions={d.term: d.choice_id for d in used})

        # 5. Compile, check and run, read-only, against this house's file only.
        query = compile_spec(spec)
        try:
            check_sql(query.sql)
            result = run_query(tenant, query.sql, query.params)
        except (UnsafeQuery, QueryTimeout) as e:
            return done(Failed(f"The query was stopped: {e}"), spec_hash=executed.hash, sql=query.sql,
                        error=type(e).__name__)

        frame = complete_periods(spec, result.frame)
        caveats = [c for c in [small_cell_note(frame, spec), *metric_caveats(spec)] if c]
        if result.truncated:
            caveats.append("Only the first rows are shown.")
        answer = Answer(
            executed=executed, sql=query.sql, params=query.params, frame=frame, text=narrate(spec, frame),
            caveats=caveats, definitions=used, truncated=result.truncated, elapsed_ms=result.elapsed_ms,
            llm_mode=llm_mode,
        )
        return done(answer, spec_hash=executed.hash, spec=executed.model_dump(mode="json"), sql=query.sql,
                    row_count=len(frame), truncated=result.truncated, query_ms=result.elapsed_ms, ai_assisted=True)

    def define(self, session: Session, term: str, choice_id: str) -> None:
        self.store.save(session.tenant_id, term, choice_id, session.user_id)
        self.audit.write(tenant=session.tenant_id, user=session.user_id, role=session.role, outcome="define",
                         term=term, choice_id=choice_id)


def complete_periods(spec: QuerySpec, frame: pd.DataFrame) -> pd.DataFrame:
    """Months with no events still appear, as zeros, when the period is bounded."""
    bounds = spec.time_window.bounds()
    if spec.group_by != ["month"] or not bounds or "n" not in frame.columns or spec.metric == "occupancy":
        return frame
    end = min(bounds[1], AS_OF)
    months = pd.period_range(bounds[0], end, freq="M").strftime("%Y-%m")
    out = pd.DataFrame({"month": months}).merge(frame, on="month", how="left")
    out["n"] = out["n"].fillna(0).astype(int)
    return out


def metric_caveats(spec: QuerySpec) -> list[str]:
    notes = []
    bounds = spec.time_window.bounds()
    if bounds and bounds[0] < date(2024, 7, 5):
        notes.append("The data starts in July 2024, so earlier months are empty or incomplete.")
    if spec.metric in ("followup_outcomes", "followup_engaged_rate"):
        notes.append("Includes everyone whose follow-up date has passed, including people who left early. "
                     "Nobody is left out for being hard to reach.")
    if spec.metric == "occupancy":
        notes.append("Counted each night: a resident fills a bed from admission up to, not including, discharge.")
    if spec.metric == "residents_now":
        notes.append(f"Status as of the extract date, {AS_OF:%d %b %Y}.")
    if spec.metric == "referrals_by_note":
        notes.append("Read from staff notes by rules and a model. Not yet confirmed by staff; recorded fields are unchanged.")
    return notes
