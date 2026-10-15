"""CLI del Job Hunter: `python -m hunter <comando>` (desde la carpeta `hunter/`).

Comandos de la Fase 1:
  init                  crea data/, el token local, el perfil y activa las reglas de ejemplo
  run                   ingesta + guillotina (las que pasan quedan pendientes del juez de la Fase 2)
  rules show|export     muestra o exporta las reglas activas
  rules import FICHERO  valida, guarda y activa unas reglas, y re-evalúa las ofertas recientes
  simulate FICHERO      qué cambiaría con otras reglas (sin guardar nada ni gastar tokens)
  jobs                  lista ofertas (por defecto, las pendientes del juez)
  sources               estado del circuit breaker de cada fuente
  purge                 borra ofertas antiguas sin gestionar (conserva sus huellas)
"""

import argparse
import asyncio
import json
import logging
import secrets
import shutil
import sys
from datetime import timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import httpx
from app.core.logging import RedactSecretsFilter, setup_logging
from pydantic import ValidationError

from hunter.config import HUNTER_ROOT, Settings, get_settings
from hunter.models import Run
from hunter.pipeline.prescore import load_profile_terms
from hunter.pipeline.run import Pipeline, PipelineConfig, RunInProgressError
from hunter.pipeline.simulate import simulate
from hunter.rules.schema import GoldenRules
from hunter.sources import breaker
from hunter.sources.registry import build_sources
from hunter.store.db import connect
from hunter.store.repository import Repository, utcnow

EXAMPLE_RULES = HUNTER_ROOT / "rules.example.json"
EXAMPLE_PROFILE = HUNTER_ROOT / "profile.example.md"
ENV_FILE = HUNTER_ROOT / ".env"

_STATUS_LABEL = {
    "ok": "ok",
    "empty": "sin resultados",
    "blocked": "BLOQUEADA",
    "timeout": "TIMEOUT",
    "error": "ERROR",
    "skipped_breaker_open": "en pausa (circuit breaker)",
}


def _configure_logging(settings: Settings) -> None:
    setup_logging(settings.log_level)
    log_dir = settings.db_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        log_dir / "hunter.log", when="midnight", backupCount=14, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactSecretsFilter())
    logging.getLogger().addHandler(handler)


def _repo(settings: Settings) -> Repository:
    return Repository(connect(settings.db_path))


def _require_rules(repo: Repository) -> GoldenRules:
    rules = repo.active_rules()
    if rules is None:
        sys.exit("No hay reglas activas. Ejecuta primero: python -m hunter init")
    return rules


def _load_rules_file(path: str) -> GoldenRules:
    try:
        return GoldenRules.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        sys.exit(f"No se puede leer {path}: {exc}")
    except ValidationError as exc:
        lines = [f"  - {'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        sys.exit("Las reglas no son válidas:\n" + "\n".join(lines))


def _pipeline(repo: Repository, rules: GoldenRules, settings: Settings) -> Pipeline:
    return Pipeline(
        repo,
        rules,
        PipelineConfig(
            source_timeout_s=settings.hunter_source_timeout_s,
            breaker=_policy(settings),
            dedup_window_days=settings.hunter_dedup_window_days,
            profile_terms=load_profile_terms(_profile_path(rules)),
        ),
    )


def _policy(settings: Settings) -> breaker.BreakerPolicy:
    return breaker.BreakerPolicy(
        settings.hunter_breaker_threshold,
        settings.hunter_breaker_cooldown_h,
        settings.hunter_breaker_max_cooldown_h,
    )


# --- Comandos --------------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace, settings: Settings) -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.write_text(
            "# Generado por `python -m hunter init`. No lo subas al repositorio.\n"
            f"HUNTER_TOKEN={secrets.token_urlsafe(32)}\n"
            "# GROQ_API_KEY=gsk_...   (Fase 2: juez IA)\n",
            encoding="utf-8",
        )
        print(f"Creado {ENV_FILE} con un token local nuevo.")
    repo = _repo(settings)
    rules = repo.active_rules()
    if rules is None:
        rules = _load_rules_file(str(EXAMPLE_RULES))
        version = repo.save_rules(rules)
        print(
            f"Reglas de ejemplo activadas (versión {version}). Ajústalas con `rules export` + `rules import`."
        )
    profile = _profile_path(rules)
    if not profile.exists():
        profile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXAMPLE_PROFILE, profile)
        print(f"Creado {profile}: edítalo con tus habilidades reales.")
    print(f"Base de datos lista en {settings.db_path}")


def _profile_path(rules: GoldenRules) -> Path:
    path = Path(rules.judge.profile_file)
    return path if path.is_absolute() else HUNTER_ROOT / path


def cmd_run(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    rules = _require_rules(repo)
    pipeline = _pipeline(repo, rules, settings)

    async def go() -> Run:
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            sources = build_sources(rules, client, settings.hunter_source_pause_s)
            if args.only:
                sources = [s for s in sources if s.name in args.only]
            return await pipeline.run(sources, trigger=args.trigger, mode=args.mode)

    try:
        run = asyncio.run(go())
    except RunInProgressError as exc:
        sys.exit(str(exc))
    if settings.hunter_retention_days > 0:
        _purge(repo, settings)
    _print_run(run)
    if run.status == "failed":
        sys.exit(1)


def _print_run(run: Run) -> None:
    c = run.counts
    print(f"\nRun {run.id[:8]} · {run.status.upper()} · reglas {run.rules_version}")
    for s in run.sources:
        line = f"  {s.source:<12} {_STATUS_LABEL.get(s.status, s.status):<28} {s.valid:>4} ofertas"
        if s.invalid:
            line += f" ({s.invalid} filas inválidas)"
        line += f" · {s.duration_ms / 1000:.1f} s"
        if s.error_code or s.error_message:
            line += f" · {s.error_code or ''} {s.error_message or ''}".rstrip()[:120]
        if s.retry_at:
            line += f" · reintento {s.retry_at.astimezone():%d/%m %H:%M}"
        print(line)
    print(
        f"  Leídas {c.fetched} · nuevas {c.new} · duplicadas {c.duplicates} · "
        f"descartadas {c.discarded} · pendientes del juez {c.pending_judge}"
    )


def cmd_rules(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    if args.action == "import":
        if not args.file:
            sys.exit("Indica el fichero: python -m hunter rules import reglas.json")
        rules = _load_rules_file(args.file)
        version = repo.save_rules(rules)
        total, pending, discarded = _pipeline(repo, rules, settings).reevaluate(window_days=args.days)
        print(
            f"Reglas {version} activadas. Re-evaluadas {total} ofertas de los últimos {args.days} días: "
            f"{pending} vuelven a pendientes, {discarded} pasan a descartadas."
        )
        return
    rules = _require_rules(repo)
    text = json.dumps(rules.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.action == "export" and args.file:
        Path(args.file).write_text(text + "\n", encoding="utf-8")
        print(f"Reglas {rules.version} exportadas a {args.file}")
    else:
        print(text)
        print(f"\n# versión {rules.version}")


def cmd_simulate(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    current = _require_rules(repo)
    report = simulate(repo, current, _load_rules_file(args.file), window_days=args.days)
    print(f"Últimos {report.window_days} días: {report.total} ofertas")
    print(f"  Ahora:     {report.current.kept} pasan · {report.current.discarded} descartadas")
    print(f"  Propuesta: {report.proposed.kept} pasan · {report.proposed.discarded} descartadas")
    if report.by_rule:
        print(
            "  Descartes por regla (propuesta): " + ", ".join(f"{k} {v}" for k, v in report.by_rule.items())
        )
    for title, items, total in (
        ("Nuevas descartadas", report.newly_discarded, report.newly_discarded_total),
        ("Nuevas que pasan", report.newly_kept, report.newly_kept_total),
    ):
        if total:
            print(f"\n{title} ({total}):")
            for item in items:
                print(f"  - {item.title} · {item.company} — {item.rule_label}")


def cmd_jobs(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    jobs = repo.jobs_seen_since(utcnow() - timedelta(days=args.days), (args.stage,))
    if args.stage == "pending_judge":
        jobs.sort(key=lambda j: j.prescore, reverse=True)
    for job in jobs[: args.limit]:
        line = (
            f"[{job.prescore:>3}] {job.title} · {job.company} · {job.location or '¿?'} ({job.facts.modality})"
        )
        print(line)
        if args.stage == "discarded":
            g = repo.latest_guillotine(job.id)
            if g and g.rule_label:
                print(f"       ✗ {g.rule_label}" + (f" — «{g.matched_text[:90]}»" if g.matched_text else ""))
        print(f"       {job.url}")
    print(
        f"\n{min(len(jobs), args.limit)} de {len(jobs)} ofertas en '{args.stage}' "
        f"(últimos {args.days} días). "
        f"Total por etapa: {repo.count_by_stage()}"
    )


def cmd_sources(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    policy = _policy(settings)
    now = utcnow()
    healths = repo.all_source_health()
    if not healths:
        print("Aún no se ha ejecutado ninguna fuente.")
    for h in healths:
        state = breaker.state(h, now, policy)
        extra = f" hasta {h.open_until.astimezone():%d/%m %H:%M}" if state == "open" and h.open_until else ""
        ok = f" · último ok {h.last_ok_at.astimezone():%d/%m %H:%M}" if h.last_ok_at else ""
        err = f" · {h.last_error[:80]}" if h.last_error else ""
        print(f"  {h.source:<14} {state}{extra} · fallos seguidos {h.consecutive_failures}{ok}{err}")


def _purge(repo: Repository, settings: Settings) -> int:
    now = utcnow()
    days = settings.hunter_retention_days
    return repo.purge(now - timedelta(days=days), now - timedelta(days=days * 2))


def cmd_purge(args: argparse.Namespace, settings: Settings) -> None:
    removed = _purge(_repo(settings), settings)
    print(
        f"Purgadas {removed} ofertas de más de {settings.hunter_retention_days} días (huellas conservadas)."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hunter", description="Job Hunter (ver SPEC.md)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="prepara data/, el token, el perfil y las reglas de ejemplo")

    run = sub.add_parser("run", help="busca ofertas y aplica la guillotina")
    run.add_argument(
        "--mode",
        choices=["ingest_only"],
        default="ingest_only",
        help="el juez IA (full/judge_only) llega en la Fase 2",
    )
    run.add_argument("--trigger", choices=["cli", "scheduler"], default="cli")
    run.add_argument(
        "--only", nargs="+", metavar="FUENTE", help="limitar a estas fuentes (p. ej. indeed remotive)"
    )

    rules = sub.add_parser("rules", help="ver, exportar o importar las Reglas de Oro")
    rules.add_argument("action", choices=["show", "export", "import"])
    rules.add_argument("file", nargs="?")
    rules.add_argument("--days", type=int, default=7, help="ventana de re-evaluación al importar")

    sim = sub.add_parser("simulate", help="qué cambiaría con otras reglas (no guarda nada)")
    sim.add_argument("file")
    sim.add_argument("--days", type=int, default=7)

    jobs = sub.add_parser("jobs", help="lista ofertas guardadas")
    jobs.add_argument(
        "--stage", choices=["pending_judge", "discarded", "judged", "judge_failed"], default="pending_judge"
    )
    jobs.add_argument("--days", type=int, default=7)
    jobs.add_argument("--limit", type=int, default=30)

    sub.add_parser("sources", help="estado de las fuentes (circuit breaker)")
    sub.add_parser("purge", help="borra ofertas antiguas sin gestionar")
    return parser


COMMANDS = {
    "init": cmd_init,
    "run": cmd_run,
    "rules": cmd_rules,
    "simulate": cmd_simulate,
    "jobs": cmd_jobs,
    "sources": cmd_sources,
    "purge": cmd_purge,
}


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # consola de Windows
    args = build_parser().parse_args(argv)
    settings = get_settings()
    _configure_logging(settings)
    COMMANDS[args.command](args, settings)


if __name__ == "__main__":
    main()
