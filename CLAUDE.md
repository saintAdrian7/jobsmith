# jobsmith — Operator Manual

A standalone pipeline: sources job leads, scores them against an ideal employer
profile, generates tailored artifacts per employer. State is files; every data
folder has an INDEX.md describing its schema.

## Modules and flow

truth/ (candidate data) + leads/ (sourced employers) -> outputs/ (artifacts) -> outbound/ (tracking)

Code lives in pipeline/. Stages communicate only via files, so any stage can rerun independently.

## Commands

    python -m pipeline source [--source ats|exa|apify]
    python -m pipeline score [--all]
    python -m pipeline generate <lead_id> | --top N [--force]
    python -m pipeline status
    python -m pipeline mark <lead_id> <generated|applied|replied|rejected>

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill keys you have (ATS source needs none).
3. Fill `iep.yaml` (five criteria + must-rules), `truth/resume.md`, `truth/facts.yaml`.
4. Add company slugs / query / actor in `config.yaml`.

## Extending

- New source: one file in pipeline/sources/ implementing fetch(criteria) -> list[Lead],
  decorated with @register. Missing prerequisites raise SourceUnavailable.
- New LLM provider: subclass BaseProvider in pipeline/llm/, add to get_provider's dict.
- Outbound sending: new module consuming outbound/applications.json entries with
  status "generated". Not built in v1 by design.

## Constraints (binding for all code changes; reviewers gate on these)

1. Simplest approach that fully achieves the goal and scales to it.
2. Reusable, cleanly separated, independently testable components.
3. Readable code; type hints and one-line contract docstrings; no other comments.
4. Machine-readable state and predictable interfaces — built for AI operators too.
5. LLM layer stays provider-agnostic.

## Testing

`pytest` — no network, no keys. Sources use httpx.MockTransport fixtures; LLM
tests use fakes. Every component is also runnable standalone (sources via
`python -m pipeline.sources.<name>`).
