# jobsmith

Four-module job application system: a structured source of truth, lead sourcing
against an ideal employer profile (IEP), per-employer tailored outputs, and
application tracking.

    truth/ ──┐
             ├──> outputs/<lead_id>/ (resume, cover letter, recommendations)
    leads/ ──┘         │
    (source + score)   └──> outbound/applications.json

## Quick start

This repo template tracks `truth/`, `leads/`, `outputs/`, and `outbound/` in git. If you run the
pipeline with your real data in a public fork or clone, your resume, personal facts, and application
history get published along with the code. Run your real data in a private repo, or add those
folders to `.gitignore` first.

    pip install -r requirements.txt
    cp .env.example .env          # fill the keys you have; ATS needs none
                                   # Windows: copy .env.example .env
    # fill iep.yaml, truth/resume.md, truth/facts.yaml, config.yaml
    python -m pipeline source
    python -m pipeline score
    python -m pipeline generate --top 5
    python -m pipeline status

## Design

- Filesystem as database: JSON indexes + markdown artifacts, all state inspectable.
- Three lead sources (Greenhouse/Lever ATS APIs, Exa search, Apify actors) behind
  one interface; each independently runnable and testable; missing keys skip cleanly.
- Provider-agnostic LLM layer: Anthropic or any OpenAI-compatible API (Mistral,
  Groq, Ollama) — switch in config.yaml.
- See CLAUDE.md for the operator manual.

## Tests

    pytest
