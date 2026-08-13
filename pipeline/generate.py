import json
import shutil
from pathlib import Path

from pipeline.config import ConfigError
from pipeline.store import Store

PROMPTS = {
    "resume": (
        "Tailor the candidate's resume to this specific job lead. Keep every fact truthful to "
        "the TRUTH section; reorder and reword for relevance to the lead. Output markdown only."
    ),
    "cover_letter": (
        "Write a cover letter for this lead in the candidate's own voice (see writing samples in "
        "TRUTH). Specific, warm, no clichés, under 300 words. Output markdown only."
    ),
    "recommendations": (
        "Given the lead's likely tech stack and the candidate's skills, recommend: 2-3 open source "
        "repositories worth contributing to (with what kind of PR), and 3 practice problems or "
        "topics to sharpen relevant skills. Output markdown with two sections."
    ),
}


def load_truth(root: Path) -> str:
    """Concatenate truth/ files into one context block; resume.md is required."""
    truth_dir = root / "truth"
    resume = truth_dir / "resume.md"
    if not resume.exists():
        raise ConfigError(f"Missing {resume}. Add your resume before generating.")
    parts = []
    for path in [resume, truth_dir / "facts.yaml", *sorted((truth_dir / "writing").glob("*"))]:
        if path.exists() and path.is_file():
            parts.append(f"## {path.name}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def generate_for(
    lead_id: str,
    store: Store,
    provider,
    truth: str,
    artifacts: list[str],
    force: bool = False,
) -> list[Path]:
    """Generate all artifacts for one lead; refuse to overwrite existing output without force."""
    output_dir = store.root / "outputs" / lead_id
    has_existing = output_dir.exists() and any(output_dir.iterdir())
    if not force and has_existing:
        raise FileExistsError(f"{output_dir} already has artifacts; rerun with --force to regenerate")
    backup_dir = output_dir.with_name(output_dir.name + ".bak")
    if force and has_existing:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        output_dir.rename(backup_dir)
    else:
        backup_dir = None
    lead = store.load_lead(lead_id)
    context = f"TRUTH:\n{truth}\n\nLEAD:\n{json.dumps(lead.to_dict(), indent=2)}"
    paths = []
    try:
        for name in artifacts:
            content = provider.complete(
                [
                    {"role": "system", "content": PROMPTS[name]},
                    {"role": "user", "content": context},
                ]
            )
            paths.append(store.save_artifact(lead_id, name, content))
        store.record_output(lead_id, lead.company, artifacts)
        store.set_lead_status(lead_id, "generated")
        store.mark(lead_id, "generated")
    except Exception:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        if backup_dir is not None and backup_dir.exists():
            backup_dir.rename(output_dir)
        raise
    else:
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir)
    return paths
