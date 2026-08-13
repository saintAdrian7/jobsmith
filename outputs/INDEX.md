# outputs/ — per-employer artifacts (module 3)

Written by `pipeline generate`.

- `index.json`: lead_id -> {company, artifacts: [names], generated_at}
- `<lead_id>/resume.md`, `cover_letter.md`, `recommendations.md`

Never overwritten without `--force`.
