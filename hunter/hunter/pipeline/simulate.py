"""Simulación de reglas (SPEC §8, `POST /rules/simulate`): qué cambiaría sin guardar ni gastar tokens."""

from collections import Counter
from datetime import date, timedelta

from pydantic import BaseModel, Field

from hunter.rules.engine import evaluate
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, utcnow

SAMPLE_SIZE = 20


class Tally(BaseModel):
    kept: int = 0
    discarded: int = 0


class ChangedJob(BaseModel):
    job_id: str
    title: str
    company: str
    rule_id: str | None = None
    rule_label: str | None = None


class SimulationReport(BaseModel):
    window_days: int
    total: int
    current: Tally
    proposed: Tally
    newly_discarded: list[ChangedJob] = Field(default_factory=list)
    newly_kept: list[ChangedJob] = Field(default_factory=list)
    newly_discarded_total: int = 0
    newly_kept_total: int = 0
    by_rule: dict[str, int] = Field(default_factory=dict)


def simulate(
    repo: Repository,
    current: GoldenRules,
    proposed: GoldenRules,
    window_days: int = 7,
    today: date | None = None,
) -> SimulationReport:
    now = utcnow()
    today = today or now.date()
    jobs = repo.jobs_seen_since(now - timedelta(days=window_days))
    report = SimulationReport(window_days=window_days, total=len(jobs), current=Tally(), proposed=Tally())
    by_rule: Counter[str] = Counter()
    for job in jobs:
        before = evaluate(job.facts, current, today)
        after = evaluate(job.facts, proposed, today)
        if before:
            report.current.discarded += 1
        else:
            report.current.kept += 1
        if after:
            report.proposed.discarded += 1
            by_rule[after[0].rule_id] += 1
        else:
            report.proposed.kept += 1
        if after and not before:
            report.newly_discarded_total += 1
            if len(report.newly_discarded) < SAMPLE_SIZE:
                report.newly_discarded.append(
                    ChangedJob(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        rule_id=after[0].rule_id,
                        rule_label=after[0].rule_label,
                    )
                )
        elif before and not after:
            report.newly_kept_total += 1
            if len(report.newly_kept) < SAMPLE_SIZE:
                report.newly_kept.append(
                    ChangedJob(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        rule_id=before[0].rule_id,
                        rule_label=before[0].rule_label,
                    )
                )
    report.by_rule = dict(by_rule.most_common())
    return report
