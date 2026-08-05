"""What the hosted demo refuses, and why, in one place.

A local workspace serves the one person whose machine it runs on: it browses their folders,
indexes any repository they point at, and spends whatever model quota they are paying for.
None of that survives being put on the public internet, so hosted mode narrows it — not by
removing routes, but by refusing them with an explanation. A route that is gone is a 404
about a path; a route that refuses says what this deployment is.

Everything here is inert unless `hosted` is set, so a local run walks the same code and is
told nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from threading import Lock

from archcompass.bootstrap import Runtime


class HostedRefusal(Exception):
    """Refused because of what this deployment is, rather than what the request said.

    Its own type rather than an `ArchCompassError`: nothing about the application's state
    or the request is wrong, and the same call on a local workspace would have been served.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HostedRestrictions:
    """What a hosted instance will not do, asked one method per route."""

    hosted: bool = False

    def browsing(self) -> None:
        if not self.hosted:
            return
        raise HostedRefusal(
            403,
            "hosted_restriction",
            "This is the hosted demo, so the folder picker is switched off: the server's "
            "filesystem is not yours to look through. Load one of the bundled examples "
            "instead, or run Arch Compass locally to review your own repository.",
        )

    def checkout(self) -> None:
        """Cloning is refused outright on the demo, rather than narrowed to a safe list.

        A URL the visitor chooses is a request this server makes on their behalf, to an
        address only they picked — which is somebody else's bandwidth, this instance's disk,
        and a reachability probe of whatever is behind it. There is no version of that worth
        offering on a public demo, and the bundled examples are already the answer to what a
        visitor is here to see.
        """

        if not self.hosted:
            return
        raise HostedRefusal(
            403,
            "hosted_restriction",
            "This is the hosted demo, so it will not clone a repository: it reviews only the "
            "examples it ships with. Run Arch Compass locally to point it at your own code.",
        )

    def policy_source(self) -> None:
        if not self.hosted:
            return
        raise HostedRefusal(
            403,
            "hosted_restriction",
            "This is the hosted demo, so a folder on the server cannot be registered as a "
            "policy source. Policies you write here are kept in your own workspace and are "
            "read by every review you run.",
        )

    def repository_root(self, root: Path, runtime: Runtime) -> Path:
        """The repository this request may index, or a refusal naming what it may.

        Resolved and compared as paths rather than as strings: `..` and a symlink both make
        a prefix test say yes about a directory that is somewhere else entirely.
        """

        canonical = root.expanduser().resolve(strict=False)
        if not self.hosted:
            return canonical
        bundled = [
            Path(example.repository_root).resolve(strict=False)
            for example in runtime.bundled_example_service.list()
        ]
        if any(canonical == item or canonical.is_relative_to(item) for item in bundled):
            return canonical
        raise HostedRefusal(
            403,
            "hosted_restriction",
            "This is the hosted demo, so it only indexes the repositories it ships with. "
            "Pick a bundled example, or run Arch Compass locally to point it at your own "
            "code.",
        )


class RunBudget:
    """Daily caps on the endpoints that spend model tokens.

    The demo runs on a metered free tier, and one visitor holding down a button is enough to
    spend the day's quota for everyone. Two caps rather than one: the per-session cap stops
    that visitor, the global cap stops the day costing more than it is worth however many
    visitors there are.

    Counters live in this process and nowhere else. A cold start forgets them, and two
    instances count separately — so the global cap is a ceiling per instance, not a
    guarantee. That is the honest trade for a demo: the alternative is Redis, and the
    failure mode here is a slightly generous day rather than a bill.

    Counted on admission rather than on completion, because a run that fails halfway has
    already spent the tokens it made.
    """

    def __init__(self, *, session_daily_runs: int, global_daily_runs: int) -> None:
        self._session_limit = session_daily_runs
        self._global_limit = global_daily_runs
        self._lock = Lock()
        self._day = _utc_day()
        self._sessions: dict[str, int] = {}
        self._total = 0

    def admit(self, token: str) -> None:
        with self._lock:
            self._roll_over()
            if self._total >= self._global_limit:
                raise self._refusal(
                    "This is a shared free-tier demo and it has spent today's model budget "
                    "for everyone."
                )
            spent = self._sessions.get(token, 0)
            if spent >= self._session_limit:
                raise self._refusal(
                    "This is a shared free-tier demo and you have used your share of "
                    f"today's model budget ({self._session_limit} runs)."
                )
            self._sessions[token] = spent + 1
            self._total += 1

    def _roll_over(self) -> None:
        today = _utc_day()
        if today != self._day:
            self._day = today
            self._sessions.clear()
            self._total = 0

    def _refusal(self, reason: str) -> HostedRefusal:
        return HostedRefusal(
            429,
            "budget_exhausted",
            f"{reason} It resets at midnight UTC, {_next_reset().isoformat()}. Run Arch "
            "Compass locally against your own model to review without a budget.",
        )


def _utc_day() -> date:
    return datetime.now(UTC).date()


def _next_reset() -> datetime:
    return datetime.combine(
        datetime.now(UTC).date() + timedelta(days=1), time(), tzinfo=UTC
    )
