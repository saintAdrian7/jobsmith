# Job Search Pipeline — Design

Date: 2026-08-13
Status: Approved

## Context

Assignment (due 6pm EAT, first draft): a public repo implementing a four-module job
application system — a structured source of truth, lead generation against an ideal
employer profile (IEP), per-employer tailored outputs, and outbound. KPIs it serves:
application volume, tailoring ability, public posts, open-source contributions,
problems solved.

## Constraints (binding on all implementation and review)

1. Simplest approach that fully achieves the goal and scales to it. Complexity is
   added only when needed for the desired output.
2. Reusable, cleanly separated components. Each component and function is reliable,
   independently understandable, and independently testable.
3. Readable code. No unnecessary comments. Type hints and one-line contract
   docstrings only.
4. Built for AI operators as much as humans: machine-readable state, self-describing
   indexes, predictable CLI contracts. An agent must be able to operate any part
   without reading its internals.
5. Provider-agnostic LLM layer — not tied to Anthropic.

## Decisions made

- Standalone Python pipeline (not Claude-Code-as-engine). No frameworks, no DB.
- Filesystem as database: JSON indexes + markdown artifacts. All state inspectable
  with `ls` and `cat`.
- Three lead sources wired at v1 — ATS APIs (Greenhouse/Lever), Exa, Apify — each
  independently runnable and testable behind one interface.
- Outbound v1 is tracking only (`applications.json`); no sending. Module boundary
  shaped so an SMTP sender drops in later.
- `iep.yaml` ships with placeholders for the user's five criteria (roles, seniority,
  remote policy, company stage, disqualifiers); user fills values.
- Two LLM providers to prove the abstraction: Anthropic + an OpenAI-compatible
  client (covers Mistral, OpenAI, Groq, Ollama).

## Repo layout

```
CLAUDE.md            operator manual: module relations, commands, contracts, review rubric
README.md
iep.yaml             ideal employer profile (5 placeholder criteria; must/prefer split)
config.yaml          provider choice, source toggles, paths, thresholds
.env.example         ANTHROPIC_API_KEY, EXA_API_KEY, APIFY_TOKEN, MISTRAL_API_KEY
truth/               [module 1] user's data
  INDEX.md           schema docs for this folder
  resume.md
  facts.yaml         structured facts: skills, links, work authorization, constraints
  writing/           past cover letters/posts — voice samples
leads/               [module 2] sourced employers
  INDEX.md
  index.json         lead_id -> {company, title, url, source, score, status, sourced_at}
  <lead_id>.json     full lead record
outputs/             [module 3] per-employer artifacts
  INDEX.md
  index.json         lead_id -> {company, artifacts: [names], generated_at}
  <lead_id>/         resume.md, cover_letter.md, recommendations.md
outbound/            [module 4] tracking only in v1
  INDEX.md
  applications.json  lead_id -> generated|applied|replied|rejected
pipeline/
  cli.py             python -m pipeline <command>; thin argument parsing only
  config.py          loads config.yaml + env; fails fast naming missing config
  models.py          Lead + artifact dataclasses
  store.py           ALL index/file IO; atomic writes (temp + rename)
  filter.py          deterministic prefilter from iep.yaml `must` rules; pure function
  generate.py        truth + lead -> artifacts via llm.complete()
  sources/           Source protocol + registry; ats.py, exa.py, apify.py
  llm/               complete() interface + registry; anthropic.py, openai_compat.py
tests/
```

## Data contracts

**Lead** — the one shape every source produces:
`id` (sha256 of `company|job_url` — deterministic, gives free dedup), `company`,
`title`, `url`, `location`, `remote: bool|null`, `description`, `source`,
`contact_email: str|null`, `sourced_at`. Scoring adds `score: 0-1` and
`score_rationale`.

**iep.yaml** — five criteria, split `must` (deterministic prefilter kills violators)
and `prefer` (feeds LLM scoring).

**Indexes** — every data folder has `index.json` (machine API: one entry per record
with current status) and `INDEX.md` (schema documentation). Agents read `INDEX.md`
once to learn the schema, then operate on `index.json`.

## Component contracts

- `sources/*`: implement `fetch(criteria) -> list[Lead]`. ATS hits Greenhouse/Lever
  public JSON endpoints (no key). Exa/Apify self-skip with a clear notice when their
  key is absent. Registry maps names to implementations; adding a source is one file
  plus one registration line. Each source is a CLI entry point for standalone smoke
  tests.
- `llm/`: `complete(messages, *, json_schema=None) -> str | dict`. Provider selected
  in config.yaml. No LLM framework.
- `filter.py`: pure function applying `must` rules so obvious rejects never cost
  tokens.
- `generate.py`: assembles context (full truth/, one lead, tone guidance from
  writing samples), calls `complete()` per artifact, writes the employer's output
  folder including `recommendations.md` (OSS repos to PR, problems to solve).
- `store.py`: the only code touching `index.json` files. Swap-point if files ever
  give way to SQLite.

## Commands (one per stage; stages communicate only via files)

```
pipeline source [--source ats|exa|apify]   fetch -> normalize -> prefilter -> dedup -> leads/
pipeline score  [--new|--all]              LLM scores leads against iep.yaml prefer-criteria
pipeline generate <lead_id> | --top N      truth x lead -> outputs/<lead_id>/
pipeline status                            counts + states across all four indexes
pipeline mark <lead_id> <status>           update outbound tracker
```

## Error handling

- Per-source isolation: one source failing does not kill `source`; run summary
  reports per-source outcomes (sourced/skipped/failed with reason).
- LLM: retry with backoff on transient errors. Schema-validated JSON outputs get one
  re-ask on invalid, then fail that lead loudly and continue the batch.
- Never overwrite an existing output folder without `--force`.
- Missing config fails fast at startup, naming exactly what is missing.

## Testing

`pytest`, no network, no keys required:
- sources against canned HTTP fixtures shaped like real Greenhouse/Lever/Exa/Apify
  responses
- generate with a fake provider returning fixed completions
- store on tmp dirs: dedup, atomicity
- filter as pure-function table tests
- CLI smoke test per command

## Build process

Subagent-driven: each component is built by a dedicated agent, then reviewed against
two gates before shipping:
1. Works: tests pass, runs standalone.
2. Honors constraints 1-5 above.
Fail either gate: back to the builder with specific findings. The rubric lives in
CLAUDE.md so agents read standards from the repo.

## Out of scope (v1)

Outbound sending (SMTP/API apply), browser auto-apply, UI, SQLite, vector stores,
scheduling/orchestration frameworks.
