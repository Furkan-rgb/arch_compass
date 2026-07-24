from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationReport:
    summary: str
    findings: list[str]
    policies: list[str]


@dataclass(frozen=True)
class CompletedRun:
    report: RecommendationReport


@dataclass(frozen=True)
class ReportAnswer:
    text: str
