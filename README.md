# Harbourview House analytics

A take-home for Axon: a director's status board and funder report for a fictional recovery home
(Task A), staff notes read into structured fields with a review queue, a prototype that answers
plain-English questions with checked, read-only queries (Task B), and short written answers
(Task C). All data is synthetic.

- [WRITEUP.md](WRITEUP.md): one-page summary and Task C answers
- [DECISIONS.md](DECISIONS.md): every decision, the options considered, and why
- [docs/architecture.md](docs/architecture.md): notes-to-fields and question-to-chart designs, safety, PHI, evaluation
- [eval/NOTES_REPORT.md](eval/NOTES_REPORT.md) and [eval/REPORT.md](eval/REPORT.md): evaluation scores

## Run it

Needs [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and every dependency.

```bash
uv sync
uv run axon build                          # builds one read-only DuckDB file per house
uv run streamlit run app/streamlit_app.py  # opens the app at http://localhost:8501
```

Other commands:

```bash
uv run pytest                              # 143 tests
uv run axon eval                           # score the 40 evaluation questions from recordings
uv run axon notes-eval                     # score note extraction on 65 labelled notes
uv run axon report --fy 2025               # write the funder report to out/
uv run python scripts/generate_data.py     # regenerate the second house (seeded, deterministic)
```

### Questions and the API key

The app and the evaluation work offline by replaying recorded model answers in
`eval/cassettes/`. To ask new questions, or to re-record after changing the prompt or model,
copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. `AXON_LLM_MODE` can be `auto`
(default: use a recording if there is one, otherwise call the API), `replay`, `record` or `live`.

```bash
uv run axon eval --mode record                            # re-record and re-score
uv run axon eval --mode record --model claude-sonnet-5-5  # compare another model
```

## What's where

```
data/raw/            harbourview_residents.csv (given), northshore_residents.csv (generated)
src/axon/
  ingest.py          read and type-check a house's CSV
  model.py           build the shared tables: residents, followups, nightly_census
  quality.py         data-quality rules, each with its treatment
  metrics/           funnel, occupancy, length of stay, outcomes
  status.py          the status board flags and the notes review queue
  notes/             staff notes to fields: schema, rules, model, merge, review, evaluation
  suppress.py        small-count hiding for the funder report
  redact.py          PHI redaction for notes and questions
  synth.py           seeded generator for extra houses
  agent/             catalogue, spec, compiler, SQL guard, executor, glossary,
                     house definitions, prompt, LLM client, answer templates, audit log
  report/funder.py   the funder export
app/                 Streamlit app (status board, staff notes, questions, funder report, data quality)
eval/                labelled questions, recordings, report
tests/               metric edge cases, privacy, query safety, tenant isolation, agent flow
```

## Sign-in (demo)

The app has a demo sign-in to show role-based views: a director sees everything for their
house; a funder sees only the published report with small counts hidden; a director of the
second house sees only that house. In production the identity provider sets the house and role.

## How AI was used

I used Claude (Claude Code) as a pair programmer for this take-home. I made the decisions: every
metric definition, design choice and trade-off in DECISIONS.md was laid out as options and chosen
by me. Claude wrote much of the code and first drafts of the documents to those decisions; I
reviewed, ran and changed them.
