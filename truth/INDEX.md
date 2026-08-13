# truth/ — source of truth (module 1)

Everything the pipeline knows about the candidate. Consumed whole by `pipeline generate`.

| File | Purpose |
|---|---|
| resume.md | Starter resume, markdown. REQUIRED before generating. |
| facts.yaml | Structured facts: skills, links, work authorization, constraints. |
| writing/ | Past cover letters and posts — voice samples for tone matching. |

No index.json here: this folder is read in full, not queried by id.
