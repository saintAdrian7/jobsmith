# jobsmith

Four-module job application system: a structured source of truth, lead sourcing
against an ideal employer profile (IEP), per-employer tailored outputs, and
application tracking.

    truth/ ──┐
             ├──> outputs/<lead_id>/ (resume, cover letter, recommendations)
    leads/ ──┘         │
    (source + score)   └──> outbound/applications.json

## Quick start

    pip install -r requirements.txt
    copy .env.example .env        # fill the keys you have; ATS needs none
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
