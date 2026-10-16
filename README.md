# Harbourview House analytics

A take-home for Axon: a director's status board and funder report for a fictional recovery home
(Task A), staff notes read into structured fields with a review queue, a prototype that answers
plain-English questions with checked, read-only queries (Task B), and short written answers
(Task C). All data is synthetic.

- [WRITEUP.md](WRITEUP.md): one-page summary and Task C answers
- [DECISIONS.md](DECISIONS.md): every decision, the options considered, and why
- [docs/architecture.md](docs/architecture.md): notes-to-fields and question-to-chart designs, safety, PHI, evaluation
- [docs/Harbourview_design_and_reasoning.docx](docs/Harbourview_design_and_reasoning.docx): the design, with diagrams, for review
- [docs/review/evaluation_review.xlsx](docs/review/evaluation_review.xlsx): the question set and labelled notes, to check
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
uv run axon eval                           # score the 44 evaluation questions from recordings
uv run axon notes-eval                     # score note extraction on 65 labelled notes
uv run axon report --fy 2025               # write the funder report to out/
uv run python scripts/generate_data.py     # regenerate the second house (seeded, deterministic)
```

### The language model (free, local, nothing leaves the machine)

The model step runs on an open model on your own computer, standing in for a model self-hosted in
Axon's AWS account in Canada. No API key and no paid service are needed.

```bash
brew install ollama
ollama serve                 # in its own terminal
ollama pull gemma3:12b       # Google Gemma 3, 12B, about 8 GB
```

Without the model running, the app and both evaluations replay recorded answers from
`eval/cassettes/`, so everything still works offline for the recorded questions. With it running,
new questions are answered live (about 10 seconds each on a laptop) and recorded.
`AXON_LLM_MODE` can be `auto` (default), `replay`, `record` or `live`.

```bash
uv run axon eval --mode record          # re-run the 44 questions through the model
uv run axon notes-eval --mode record    # re-run the 70 labelled notes
```

## What's where

```
data/raw/            harbourview_residents.csv (given), testhouse_residents.csv (generated)
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

## The generated test house

`data/raw/testhouse_residents.csv` is invented by `scripts/generate_data.py` (seed 7). It is not part
of the brief or the given data. It exists only so the tests can prove that one house can never query
another's data, and it is not shown in the app.

## How AI was used

I used Claude (Claude Code) as a pair programmer for this take-home. I made the decisions: every
metric definition, design choice and trade-off in DECISIONS.md was laid out as options and chosen
by me. Claude wrote much of the code and first drafts of the documents to those decisions; I
reviewed, ran and changed them.
