# leads/ — sourced employers (module 2)

Written by `pipeline source` and `pipeline score`.

- `index.json`: lead_id -> {company, title, url, source, score, status, sourced_at}
- `<lead_id>.json`: full Lead record (see pipeline/models.py)

Statuses: new (sourced) -> scored (has score 0-1) -> generated (artifacts exist).
lead_id = first 16 hex chars of sha256("company|url") — deterministic, dedup key.
