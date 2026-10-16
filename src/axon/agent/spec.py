"""The structured intermediate: a JSON spec, its schema for the LLM, and its validation.

Validation runs in three layers:
1. The JSON schema sent with the request constrains the model's output to allow-listed ids.
2. Pydantic re-parses the output with extra fields forbidden (the spec has no tenant field).
3. Semantic checks: each metric's own allowed groupings, filters, charts and required parts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from axon.agent.registry import CHARTS, DECLINE_REASONS, DIMENSIONS, FILTERS, METRICS, TIME_PRESETS
from axon.config import AS_OF

MAX_GROUP_BY = 2


class SpecError(ValueError):
    pass


class Filter(BaseModel):
    """One filter: an allow-listed field, an operator allowed on that field, and its values.

    category fields: op `in` or `not_in`, values from the field's list.
    number fields:   op `between`, values = [low, high].
    """

    model_config = ConfigDict(extra="forbid")
    field: str
    op: Literal["in", "not_in", "between"] = "in"
    values: list[str | float | int] = Field(min_length=1)

    @model_validator(mode="after")
    def _known(self) -> Filter:
        f = FILTERS.get(self.field)
        if f is None:
            raise ValueError(f"unknown filter field {self.field!r}")
        if self.op not in f.ops:
            raise ValueError(f"operator {self.op!r} not allowed on {self.field}; allowed: {list(f.ops)}")
        if f.kind == "number":
            if len(self.values) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in self.values):
                raise ValueError(f"{self.field} between needs two numbers")
            if self.values[0] > self.values[1] or self.values[0] < 0:
                raise ValueError(f"{self.field} range must be 0 or more, low before high")
            return self
        bad = [v for v in self.values if v not in f.values]
        if bad:
            raise ValueError(f"values {bad} not allowed for {self.field}; allowed: {list(f.values)}")
        if f.single and len(set(self.values)) != 1:
            raise ValueError(f"{self.field} takes exactly one value")
        return self


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: Literal["all", "fy2024", "fy2025", "custom"] = "all"
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _custom(self) -> TimeWindow:
        if self.preset == "custom":
            if self.start is None or self.end is None:
                raise ValueError("a custom time window needs start and end dates")
            if self.start > self.end:
                raise ValueError("time window start is after its end")
        elif self.start is not None or self.end is not None:
            raise ValueError("start and end are only used with preset 'custom'")
        return self

    def bounds(self) -> tuple[date, date] | None:
        if self.preset == "all":
            return None
        if self.preset == "custom":
            return self.start, self.end
        year = int(self.preset[2:])
        return date(year, 1, 1), date(year, 12, 31)


class QuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    group_by: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    chart: Literal["bar", "line", "stacked_bar", "table"] = "bar"

    @field_validator("metric")
    @classmethod
    def _metric(cls, v: str) -> str:
        if v not in METRICS:
            raise ValueError(f"unknown metric {v!r}")
        return v

    @model_validator(mode="after")
    def _semantic(self) -> QuerySpec:
        m = METRICS[self.metric]
        if len(self.group_by) > MAX_GROUP_BY:
            raise ValueError(f"at most {MAX_GROUP_BY} groupings")
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("duplicate grouping")
        for g in self.group_by:
            if g not in m.dimensions:
                raise ValueError(f"{self.metric} cannot be grouped by {g!r}; allowed: {list(m.dimensions)}")
        if m.required_dimensions and not set(self.group_by) & set(m.required_dimensions):
            raise ValueError(f"{self.metric} must be grouped by one of {list(m.required_dimensions)}")
        fields = [f.field for f in self.filters]
        if len(set(fields)) != len(fields):
            raise ValueError("each filter field may appear once")
        for f in fields:
            if f not in m.filters:
                raise ValueError(f"{self.metric} cannot be filtered by {f!r}; allowed: {list(m.filters)}")
        for req in m.required_filters:
            if req not in fields:
                raise ValueError(f"{self.metric} needs a {req!r} filter")
        if m.date_column is None and self.time_window.preset != "all":
            raise ValueError(f"{self.metric} is a point-in-time count; use time_window preset 'all'")
        bounds = self.time_window.bounds()
        if bounds and bounds[0] > AS_OF:
            raise ValueError("time window starts after the data extract date")
        if self.chart not in m.charts:
            raise ValueError(f"{self.metric} cannot be drawn as {self.chart!r}; allowed: {list(m.charts)}")
        return self


class ExecutedSpec(BaseModel):
    """What actually ran: the validated spec plus any house definitions applied to it."""

    model_config = ConfigDict(extra="forbid")
    spec: QuerySpec
    definitions: dict[str, str] = Field(default_factory=dict)  # term -> choice id

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()[:12]


class LLMReply(BaseModel):
    """What the model returns. It contains no free text that is ever shown to a user."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["answer", "clarify", "decline"]
    spec: QuerySpec | None = None
    unclear_terms: list[str] = Field(default_factory=list)
    candidate_metrics: list[str] = Field(default_factory=list)
    decline_reason: Literal["row_level", "out_of_scope", "write_request", "other_house", "unsafe"] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> LLMReply:
        if self.action == "answer" and self.spec is None:
            raise ValueError("action 'answer' needs a spec")
        if self.action == "clarify" and not self.unclear_terms:
            raise ValueError("action 'clarify' needs at least one unclear term")
        if self.action == "decline" and self.decline_reason is None:
            raise ValueError("action 'decline' needs a decline_reason")
        bad = [m for m in self.candidate_metrics if m not in METRICS]
        if bad:
            raise ValueError(f"unknown candidate metrics {bad}")
        return self


def apply_patch(spec: QuerySpec, patch: dict) -> QuerySpec:
    """Force a house definition onto a spec. Filters merge by field; groupings and metric are replaced."""
    data = spec.model_dump()
    metric_changed = "metric" in patch and patch["metric"] != data["metric"]
    if "metric" in patch:
        data["metric"] = patch["metric"]
    m = METRICS[data["metric"]]
    filters = {f["field"]: f for f in data["filters"] if f["field"] in m.filters}
    for f in patch.get("filters", []):
        filters[f["field"]] = {"op": "in", **f}
    data["filters"] = list(filters.values())
    if "group_by" in patch:
        data["group_by"] = list(patch["group_by"])
    data["group_by"] = [g for g in data["group_by"] if g in m.dimensions][:MAX_GROUP_BY]
    if m.required_dimensions and not set(data["group_by"]) & set(m.required_dimensions):
        data["group_by"] = [m.required_dimensions[0], *data["group_by"]][:MAX_GROUP_BY]
    if "time_window" in patch:
        data["time_window"] = dict(patch["time_window"])
    if m.date_column is None:
        data["time_window"] = {"preset": "all", "start": None, "end": None}
    if metric_changed or data["chart"] not in m.charts:
        data["chart"] = m.charts[0]
    return QuerySpec.model_validate(data)


def llm_json_schema() -> dict:
    """Schema for structured output. Ids are enums, so the model cannot name anything off-catalogue."""
    filter_variants = [
        {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": [f.id]},
                "op": {"type": "string", "enum": list(f.ops)},
                "values": {"type": "array",
                           "items": {"type": "number"} if f.kind == "number" else {"type": "string", "enum": list(f.values)}},
            },
            "required": ["field", "op", "values"],
            "additionalProperties": False,
        }
        for f in FILTERS.values()
    ]
    spec_schema = {
        "type": "object",
        "properties": {
            "metric": {"type": "string", "enum": list(METRICS)},
            "group_by": {"type": "array", "items": {"type": "string", "enum": list(DIMENSIONS)}},
            "filters": {"type": "array", "items": {"anyOf": filter_variants}},
            "time_window": {
                "type": "object",
                "properties": {
                    "preset": {"type": "string", "enum": list(TIME_PRESETS)},
                    "start": {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
                    "end": {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
                },
                "required": ["preset", "start", "end"],
                "additionalProperties": False,
            },
            "chart": {"type": "string", "enum": list(CHARTS)},
        },
        "required": ["metric", "group_by", "filters", "time_window", "chart"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["answer", "clarify", "decline"]},
            "spec": {"anyOf": [spec_schema, {"type": "null"}]},
            "unclear_terms": {"type": "array", "items": {"type": "string"}},
            "candidate_metrics": {"type": "array", "items": {"type": "string", "enum": list(METRICS)}},
            "decline_reason": {"anyOf": [{"type": "string", "enum": list(DECLINE_REASONS)}, {"type": "null"}]},
        },
        "required": ["action", "spec", "unclear_terms", "candidate_metrics", "decline_reason"],
        "additionalProperties": False,
    }


def parse_reply(text: str) -> LLMReply:
    try:
        return LLMReply.model_validate_json(text)
    except ValueError as e:
        raise SpecError(str(e)) from e
