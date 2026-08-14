# jobsmith

Four-module job application system: a structured source of truth, lead sourcing
against an ideal employer profile (IEP), per-employer tailored outputs, and
application tracking.

    truth/ ──┐
             ├──> outputs/<lead_id>/ (resume, cover letter, recommendations)
    leads/ ──┘         │
    (source + score)   └──> outbound/applications.json

## Privacy warning

This repo template tracks `truth/`, `leads/`, `outputs/`, and `outbound/` in git. If you run the
pipeline with your real data in a public fork or clone, your resume, personal facts, and application
history get published along with the code. Run your real data in a private repo, or add those
folders to `.gitignore` first.

## Quick start

    pip install -r requirements.txt
    cp .env.example .env          # fill the keys you have; ATS needs none
                                   # Windows: copy .env.example .env
    # fill iep.yaml, truth/resume.md, truth/facts.yaml, config.yaml
    python -m pipeline source
    python -m pipeline score
    python -m pipeline generate --top 5
    python -m pipeline status

## How it works

The pipeline is four stages. Each stage reads files the previous stage wrote and
writes its own — there is no database and no hidden state, so you can inspect
everything with a file browser.

**1. You describe yourself and your ideal employer (one-time setup).**
Put your resume in `truth/resume.md`, structured facts (skills, links, work
authorization) in `truth/facts.yaml`, and optionally past cover letters in
`truth/writing/` — the generator mimics their voice. Then fill `iep.yaml` with
your target roles, seniority, remote policy, company stage, and disqualifiers.
Its `must:` block holds hard rules (e.g. remote only, no "senior" titles) that
are enforced before any AI is involved.

**2. `python -m pipeline source` — find real openings.**
Pulls live postings from three sources: Greenhouse/Lever public job boards (the
company slugs in `config.yaml`, no API key needed), Exa web search
(`EXA_API_KEY`), and an Apify scraper actor (`APIFY_TOKEN`). Sources without a
key are skipped with a notice. Every posting is checked against your `must:`
rules, deduplicated, and saved. The summary line tells you what happened:
`ats: sourced 17, filtered 485, duplicate 0`.

**3. `python -m pipeline score` — rank them.**
Sends each new lead plus your `iep.yaml` to the LLM, which returns a 0–1 fit
score with a one-sentence rationale. Leads move from status `new` to `scored`.
Run `python -m pipeline status` anytime to see counts per status.

**4. `python -m pipeline generate --top 5` — produce tailored applications.**
For your N best-scored leads (or one specific lead: `generate <lead_id>`), the
LLM combines everything in `truth/` with the job posting and writes three
tailored documents per employer. Re-running for the same lead requires
`--force`, so nothing gets overwritten by accident.

**5. Apply, then track it.**
Applying is manual in v1 — you send the generated documents yourself. Record
where you stand with `python -m pipeline mark <lead_id> applied` (statuses:
`generated`, `applied`, `replied`, `rejected`).

## Where to find everything

| What | Where |
|---|---|
| Your data (resume, facts, writing samples) | `truth/` |
| Sourced job postings, one JSON per lead | `leads/<lead_id>.json` |
| Lead list with scores and statuses | `leads/index.json` |
| **Generated resume for an employer** | `outputs/<lead_id>/resume.md` |
| **Generated cover letter** | `outputs/<lead_id>/cover_letter.md` |
| **Generated recommendations** (OSS repos to contribute to, what to practice) | `outputs/<lead_id>/recommendations.md` |
| Which employers have generated documents | `outputs/index.json` |
| Your application statuses | `outbound/applications.json` |

To match a `lead_id` to a company, check `leads/index.json` — each entry shows
the company, job title, posting URL, score, and status. The `score` and
`generate` commands also print ids next to company names. Every data folder has
an `INDEX.md` describing its exact file formats.

## Configuration

- `config.yaml` — which LLM provider/model to use, which job boards to pull
  from, the Exa search query, which artifacts to generate.
- `.env` — API keys (never committed; `.gitignore` covers it). The ATS source
  works with no keys at all.
- The LLM layer speaks Anthropic or any OpenAI-compatible API (Mistral, Groq,
  SiliconFlow, Ollama) — switch `llm.provider`, `llm.base_url`, and
  `llm.api_key_env` in `config.yaml`, no code changes.

## Design

- Filesystem as database: JSON indexes + markdown artifacts, all state inspectable.
- Three lead sources (Greenhouse/Lever ATS APIs, Exa search, Apify actors) behind
  one interface; each independently runnable and testable; missing keys skip cleanly.
- Provider-agnostic LLM layer behind one `complete()` interface.
- See CLAUDE.md for the operator manual.

## Tests

    pytest
