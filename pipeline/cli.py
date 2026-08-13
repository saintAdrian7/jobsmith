import argparse
from pathlib import Path

from pipeline.config import Config, ConfigError
from pipeline.filter import load_iep, passes_must
from pipeline.generate import generate_for, load_truth
from pipeline.llm import get_provider
from pipeline.score import score_leads
from pipeline.sources import REGISTRY, SourceUnavailable
from pipeline.store import Store


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Entry point for python -m pipeline; returns process exit code."""
    args = _parse(argv)
    root = root or Path.cwd()
    try:
        config = Config.load(root)
        store = Store(root)
        {
            "source": lambda: _source(args, config, store, root),
            "score": lambda: _score(args, config, store, root),
            "generate": lambda: _generate(args, config, store, root),
            "status": lambda: _status(store),
            "mark": lambda: store.mark(args.lead_id, args.status),
        }[args.command]()
        return 0
    except (ConfigError, FileExistsError) as e:
        print(e)
        return 1


def _parse(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments into subcommand and options."""
    parser = argparse.ArgumentParser(prog="pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source", help="fetch leads from sources")
    source.add_argument("--source", choices=sorted(REGISTRY), default=None)
    score = commands.add_parser("score", help="LLM-score leads against iep.yaml")
    score.add_argument("--all", action="store_true")
    generate = commands.add_parser("generate", help="generate artifacts for leads")
    generate.add_argument("lead_id", nargs="?", default=None)
    generate.add_argument("--top", type=int, default=None)
    generate.add_argument("--force", action="store_true")
    commands.add_parser("status", help="show pipeline state counts")
    mark = commands.add_parser("mark", help="set application status")
    mark.add_argument("lead_id")
    mark.add_argument("status", choices=["generated", "applied", "replied", "rejected"])
    return parser.parse_args(argv)


def _source(args: argparse.Namespace, config: Config, store: Store, root: Path) -> None:
    """Fetch leads from one or all sources, apply must filters, deduplicate."""
    iep = load_iep(root)
    must = iep.get("must", {})
    names = [args.source] if args.source else sorted(REGISTRY)
    for name in names:
        try:
            leads = REGISTRY[name](config).fetch(iep)
        except SourceUnavailable as e:
            print(f"{name}: skipped - {e}")
            continue
        except Exception as e:
            print(f"{name}: failed - {e}")
            continue
        sourced = filtered = duplicate = 0
        for lead in leads:
            passed, _ = passes_must(lead, must)
            if not passed:
                filtered += 1
            elif store.save_lead(lead):
                sourced += 1
            else:
                duplicate += 1
        print(f"{name}: sourced {sourced}, filtered {filtered}, duplicate {duplicate}")


def _score(args: argparse.Namespace, config: Config, store: Store, root: Path) -> None:
    """Score new leads (or all with --all) and output scores."""
    rows = score_leads(store, get_provider(config), load_iep(root), only_new=not args.all)
    for row in rows:
        print(f"{row['score']} {row['company']} {row['id']}" + (f"  error: {row['error']}" if row.get("error") else ""))


def _generate(args: argparse.Namespace, config: Config, store: Store, root: Path) -> None:
    """Generate artifacts for one lead or top N best-scored leads."""
    if not args.lead_id and not args.top:
        raise ConfigError("generate needs a LEAD_ID or --top N")
    truth = load_truth(root)
    provider = get_provider(config)
    artifacts = config.data.get("generation", {}).get("artifacts", ["resume", "cover_letter", "recommendations"])
    if args.lead_id:
        ids = [args.lead_id]
    else:
        scored = [
            (entry["score"], lead_id)
            for lead_id, entry in store.read_index("leads").items()
            if entry["status"] == "scored" and entry["score"] is not None
        ]
        ids = [lead_id for _, lead_id in sorted(scored, reverse=True)[: args.top]]
    for lead_id in ids:
        try:
            paths = generate_for(lead_id, store, provider, truth, artifacts, force=args.force)
            print(f"{lead_id}: wrote {', '.join(p.name for p in paths)}")
        except FileExistsError as e:
            if args.lead_id:
                raise
            print(f"{lead_id}: skipped - {e}")


def _status(store: Store) -> None:
    """Print count summaries for leads, outputs, and applications by status."""
    leads = store.read_index("leads")
    by_status: dict[str, int] = {}
    for entry in leads.values():
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1
    print(f"leads: {len(leads)} {by_status}")
    print(f"outputs: {len(store.read_index('outputs'))}")
    apps: dict[str, int] = {}
    for status in store.read_applications().values():
        apps[status] = apps.get(status, 0) + 1
    print(f"applications: {apps}")
