"""CLI del Job Hunter: `python -m hunter <comando>` (desde la carpeta `hunter/`).

Comandos:
  init                  crea la carpeta de datos, el token local, el perfil y activa las reglas de ejemplo
  open                  lo que hace el acceso directo: arranca la API si hace falta y abre el Buscador
  run                   ingesta + guillotina + juez IA (--mode ingest_only: sin tokens;
                        --mode rejudge: vuelve a juzgar las notas de un perfil anterior)
  show ID / rejudge ID  veredicto de una oferta / volver a juzgarla sin caché
  serve                 API local en 127.0.0.1:8001 para la vista Buscador (--idle N: se apaga sola)
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

from app.core.logging import RedactSecretsFilter, setup_logging
from pydantic import ValidationError

from hunter import launcher, services
from hunter.config import HUNTER_ROOT, Settings, get_settings
from hunter.judge.judge import JudgeOutcome, JudgeStoppedError
from hunter.judge.limiter import BudgetGuard, QuotaExhaustedError
from hunter.judge.schema import JobVerdict
from hunter.models import Run
from hunter.pipeline.run import RunInProgressError
from hunter.pipeline.simulate import simulate
from hunter.rules.schema import GoldenRules
from hunter.sources import breaker
from hunter.store.db import connect
from hunter.store.repository import Repository, StoredJob, utcnow

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
    log_dir = settings.data_dir / "logs"
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


# --- Comandos --------------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace, settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
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
    profile = services.profile_path(rules, settings)
    if not profile.exists():
        profile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXAMPLE_PROFILE, profile)
        print(f"Creado {profile}: edítalo con tus habilidades reales.")
    print(f"Base de datos lista en {settings.db_path}")
    print(f"Tus datos (base de datos, perfil y logs) viven en {settings.data_dir}")


def cmd_run(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    rules = _require_rules(repo)
    if args.mode in ("judge_only", "rejudge") and settings.server_api_key is None:
        sys.exit("Falta GROQ_API_KEY en hunter/.env para ejecutar el juez.")
    if args.retry_failed:
        print(f"{repo.reset_failed()} ofertas fallidas vuelven a la cola del juez.")
    try:
        run = asyncio.run(
            services.execute_run(
                repo,
                rules,
                settings,
                mode=args.mode,
                trigger=args.trigger,
                only=args.only,
                judge_limit=args.judge_limit,
            )
        )
    except RunInProgressError as exc:
        sys.exit(str(exc))
    except services.ProfileMissingError as exc:
        sys.exit(str(exc))
    _print_run(run, BudgetGuard(repo, settings.hunter_daily_token_budget))
    if run.status == "failed":
        sys.exit(1)


def _print_run(run: Run, budget: BudgetGuard) -> None:
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
    if run.mode in ("full", "ingest_only"):
        print(
            f"  Leídas {c.fetched} · nuevas {c.new} · duplicadas {c.duplicates} · descartadas {c.discarded}"
        )
    if run.mode != "ingest_only":
        print(
            f"  Juez: {c.judged} juzgadas ({c.cache_hits} desde caché) · {c.judge_failed} fallidas · "
            f"{run.tokens_used} tokens · quedan {budget.remaining()} de presupuesto hoy"
        )
    print(f"  Pendientes del juez: {c.pending_judge}")
    if run.error:
        print(f"  ⚠ {run.error}")


def cmd_rules(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    if args.action == "import":
        if not args.file:
            sys.exit("Indica el fichero: python -m hunter rules import reglas.json")
        rules = _load_rules_file(args.file)
        version = repo.save_rules(rules)
        total, pending, discarded = services.build_pipeline(repo, rules, settings).reevaluate(
            window_days=args.days
        )
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


_VERDICT_LABEL = {"apply": "APLICAR", "maybe": "QUIZÁ", "skip": "NO"}


def _verdict(repo: Repository, job: StoredJob) -> JobVerdict | None:
    stored = repo.cached_verdict(job.verdict_key) if job.verdict_key else None
    if stored is None or not stored.verdict_json:
        return None
    return JobVerdict.model_validate_json(stored.verdict_json)


def cmd_jobs(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    jobs = repo.jobs_seen_since(utcnow() - timedelta(days=args.days), (args.stage,))
    if args.stage == "pending_judge":
        jobs.sort(key=lambda j: j.prescore, reverse=True)
    if args.stage == "judged":
        jobs.sort(key=lambda j: j.rank_score or 0, reverse=True)
        min_score = (
            args.min_score if args.min_score is not None else _require_rules(repo).judge.min_score_to_show
        )
    for job in jobs[: args.limit]:
        if args.stage == "judged":
            verdict = _verdict(repo, job)
            if verdict is None or verdict.match_score < min_score:
                continue
            print(
                f"[{verdict.match_score:>3}] {_VERDICT_LABEL[verdict.verdict]:<7} {job.title} · "
                f"{job.company} · {job.location or '¿?'} ({job.facts.modality}) · id {job.id[:8]}"
            )
            print(f"       {verdict.summary}")
            if verdict.red_flags:
                print("       ⚑ " + " · ".join(f.text for f in verdict.red_flags[:3]))
        else:
            print(
                f"[{job.prescore:>3}] {job.title} · {job.company} · {job.location or '¿?'} "
                f"({job.facts.modality}) · id {job.id[:8]}"
            )
        if args.stage == "discarded":
            g = repo.latest_guillotine(job.id)
            if g and g.rule_label:
                print(f"       ✗ {g.rule_label}" + (f" — «{g.matched_text[:90]}»" if g.matched_text else ""))
        if args.stage == "judge_failed" and job.judge_error:
            print(f"       ✗ {job.judge_error}")
        print(f"       {job.url}")
    print(
        f"\n{min(len(jobs), args.limit)} de {len(jobs)} ofertas en '{args.stage}' "
        f"(últimos {args.days} días). "
        f"Total por etapa: {repo.count_by_stage()}"
    )


def _require_job(repo: Repository, job_id: str) -> StoredJob:
    job = repo.get_job(job_id)
    if job is None:
        sys.exit(f"No hay ninguna oferta con id {job_id}.")
    return job


def cmd_show(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    job = _require_job(repo, args.job_id)
    print(f"{job.title} · {job.company} · {job.location or '¿?'} ({job.facts.modality})")
    print(f"Etapa: {job.stage} · pre-score {job.prescore} · vista {job.times_seen} veces · {job.url}")
    verdict = _verdict(repo, job)
    if verdict is None:
        g = repo.latest_guillotine(job.id)
        if g and g.rule_label:
            print(f"Descartada: {g.rule_label}")
        if job.judge_error:
            print(f"Juez: {job.judge_error}")
        return
    print(
        f"\n{verdict.match_score}/100 · {_VERDICT_LABEL[verdict.verdict]} · "
        f"nivel {verdict.seniority_detected} ({verdict.seniority_fit}) · ranking {job.rank_score}"
    )
    print(verdict.summary)
    for title, flags in (("A favor", verdict.green_flags), ("Alertas", verdict.red_flags)):
        if flags:
            print(f"\n{title}:")
            for flag in flags:
                mark = "✓" if flag.evidence_verified else "· sin cita verificable"
                quote = f" — «{flag.evidence}»" if flag.evidence else ""
                print(f"  - {flag.text}{quote} {mark}")
    print(f"\nStack real: {', '.join(verdict.stack_core) or '—'}")
    print(f"Stack inflado: {', '.join(verdict.stack_inflated) or '—'}")
    print(f"Le falta: {', '.join(verdict.missing_must_haves) or '—'}")


def cmd_rejudge(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    rules = _require_rules(repo)
    job = _require_job(repo, args.job_id)
    if settings.server_api_key is None:
        sys.exit("Falta GROQ_API_KEY en hunter/.env para ejecutar el juez.")

    async def go() -> JudgeOutcome:
        async with services.llm_client() as client:
            judge = services.build_judge(repo, rules, settings, client)
            if judge is None:
                sys.exit("Falta GROQ_API_KEY en hunter/.env para ejecutar el juez.")
            outcome = await judge.judge(job, force=True)
            if outcome.status != "error":
                services.build_pipeline(repo, rules, settings).save_outcome(job, outcome, judge)
                if job.stage == "discarded":  # el veredicto se guarda, pero manda la guillotina
                    repo.set_stage(job.id, "discarded")
            return outcome

    try:
        outcome = asyncio.run(go())
    except (JudgeStoppedError, QuotaExhaustedError, services.ProfileMissingError) as exc:
        sys.exit(f"El juez se ha detenido: {exc}")
    if outcome.status == "error":
        sys.exit(f"Error transitorio del juez ({outcome.error}); prueba más tarde.")
    print(f"{outcome.status} · {outcome.tokens} tokens · {outcome.model}")
    cmd_show(args, settings)


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def cmd_serve(args: argparse.Namespace, settings: Settings) -> None:
    import uvicorn  # solo hace falta para servir

    from hunter.api.app import create_app

    if settings.hunter_host not in _LOOPBACK:
        sys.exit(f"HUNTER_HOST={settings.hunter_host}: la API local solo puede escuchar en 127.0.0.1.")
    if not (settings.hunter_token and settings.hunter_token.get_secret_value()):
        sys.exit("Falta HUNTER_TOKEN en hunter/.env. Ejecuta primero: python -m hunter init")
    idle = max(0, args.idle or 0)
    app = create_app(settings, idle_minutes=idle)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.hunter_host,
            port=settings.hunter_port,
            log_level=settings.log_level.lower(),
            log_config=None,
        )
    )
    # El apagado por inactividad y el botón "Apagar" de la web paran el servidor así, limpio.
    app.state.request_exit = lambda: setattr(server, "should_exit", True)
    print(f"API local en http://{settings.hunter_host}:{settings.hunter_port} (Ctrl+C para parar)")
    print(f"Orígenes permitidos: {', '.join(settings.cors_origins)}")
    if idle:
        print(f"Se apagará sola tras {idle} min sin uso.")
    server.run()


def cmd_open(args: argparse.Namespace, settings: Settings) -> None:
    try:
        url = launcher.open_buscador(settings, search=not args.no_search)
    except launcher.LauncherError as exc:
        launcher.alert(str(exc))
        sys.exit(1)
    print(f"Buscador abierto en el navegador ({url.split('#')[0]}).")


def cmd_sources(args: argparse.Namespace, settings: Settings) -> None:
    repo = _repo(settings)
    policy = services.breaker_policy(settings)
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


def cmd_purge(args: argparse.Namespace, settings: Settings) -> None:
    removed = services.purge(_repo(settings), settings)
    print(
        f"Purgadas {removed} ofertas de más de {settings.hunter_retention_days} días (huellas conservadas)."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hunter", description="Job Hunter (ver SPEC.md)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="prepara la carpeta de datos, el token, el perfil y las reglas de ejemplo")

    run = sub.add_parser("run", help="busca ofertas, aplica la guillotina y las juzga con IA")
    run.add_argument(
        "--mode",
        choices=["full", "ingest_only", "judge_only", "rejudge"],
        default="full",
        help="full: todo · ingest_only: sin juez (0 tokens) · judge_only: solo la cola del juez · "
        "rejudge: las notas de esta semana que son de un perfil anterior",
    )
    run.add_argument("--trigger", choices=["cli", "scheduler"], default="cli")
    run.add_argument(
        "--only", nargs="+", metavar="FUENTE", help="limitar a estas fuentes (p. ej. indeed remotive)"
    )
    run.add_argument("--judge-limit", type=int, metavar="N", help="juzgar como mucho N ofertas")
    run.add_argument("--retry-failed", action="store_true", help="devuelve las fallidas a la cola del juez")

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
    jobs.add_argument("--min-score", type=int, help="en 'judged': por defecto, judge.min_score_to_show")

    show = sub.add_parser("show", help="detalle de una oferta y su veredicto")
    show.add_argument("job_id", help="id o sus primeros caracteres")
    rejudge = sub.add_parser("rejudge", help="vuelve a juzgar una oferta ignorando la caché")
    rejudge.add_argument("job_id")

    serve = sub.add_parser("serve", help="arranca la API local para la vista Buscador")
    serve.add_argument(
        "--idle", type=int, metavar="MIN", help="se apaga sola tras MIN minutos sin uso (lo usa `open`)"
    )
    open_ = sub.add_parser("open", help="arranca la API si hace falta y abre el Buscador ya conectado")
    open_.add_argument(
        "--no-search", action="store_true", help="no lanzar una búsqueda aunque la última sea antigua"
    )
    sub.add_parser("sources", help="estado de las fuentes (circuit breaker)")
    sub.add_parser("purge", help="borra ofertas antiguas sin gestionar")
    return parser


COMMANDS = {
    "init": cmd_init,
    "run": cmd_run,
    "rules": cmd_rules,
    "simulate": cmd_simulate,
    "jobs": cmd_jobs,
    "show": cmd_show,
    "rejudge": cmd_rejudge,
    "serve": cmd_serve,
    "open": cmd_open,
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
