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

        Reached only when this deployment named no hosts to fetch from. Where it did, the
        route never gets here: it fetches an archive instead, over a path that has no git in
        it and no address it did not decide on before making the request.
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
        # A tree this workspace fetched for this visitor. `runtime` is the session's own, so
        # its sources directory is the session's own too: one visitor cannot name another's
        # by construction, rather than by a rule that has to get the comparison right.
        source_service = runtime.source_service
        if source_service is not None and source_service.holds(canonical):
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
            "This is the hosted demo, so it only indexes repositories it fetched for you or "
            "ships with. Pick a bundled example, or run Arch Compass locally to point it at "
            "your own code.",
        )


class _DailyBudget:
    """Two daily caps — one per session, one for everyone — and the counting behind them.

    Shared by the things a demo has to ration, because the rationing is the same shape every
    time and only the sentence differs: the per-session cap stops one visitor holding down a
    button, and the global cap stops the day costing more than it is worth however many
    visitors there are.

    Counters live in this process and nowhere else. A cold start forgets them, and two
    instances count separately — so the global cap is a ceiling per instance, not a
    guarantee. That is the honest trade for a demo: the alternative is Redis, and the failure
    mode here is a slightly generous day rather than a bill.

    Counted on admission rather than on completion, because work that fails halfway has
    already spent what it spent.
    """

    #: What is being rationed, said two ways: to everyone, and to the one visitor who has
    #: used their share. `{limit}` is filled with the per-session cap.
    exhausted_for_everyone = ""
    exhausted_for_you = ""

    def __init__(self, *, session_limit: int, global_limit: int) -> None:
        self._session_limit = session_limit
        self._global_limit = global_limit
        self._lock = Lock()
        self._day = _utc_day()
        self._sessions: dict[str, int] = {}
        self._total = 0

    def admit(self, token: str) -> None:
        with self._lock:
            self._roll_over()
            if self._total >= self._global_limit:
                raise self._refusal(self.exhausted_for_everyone)
            spent = self._sessions.get(token, 0)
            if spent >= self._session_limit:
                raise self._refusal(
                    self.exhausted_for_you.format(limit=self._session_limit)
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


class RunBudget(_DailyBudget):
    """The cap on the endpoints that spend model tokens, on a metered free tier."""

    exhausted_for_everyone = (
        "This is a shared free-tier demo and it has spent today's model budget for everyone."
    )
    exhausted_for_you = (
        "This is a shared free-tier demo and you have used your share of today's model "
        "budget ({limit} runs)."
    )

    def __init__(self, *, session_daily_runs: int, global_daily_runs: int) -> None:
        super().__init__(session_limit=session_daily_runs, global_limit=global_daily_runs)


class FetchBudget(_DailyBudget):
    """The cap on fetching a repository, which spends disk rather than tokens.

    Its own budget rather than a share of the model one, because the two run out for
    different reasons and at different rates: a fetch costs bandwidth and — on a container
    whose writable filesystem is memory — the instance's headroom, while a review costs
    somebody's quota. Rationing them together would mean one visitor's large repository
    quietly buying fewer reviews for everybody.
    """

    exhausted_for_everyone = (
        "This demo has fetched as many repositories as it will today, for everyone."
    )
    exhausted_for_you = (
        "You have fetched as many repositories as this demo allows in a day ({limit})."
    )

    def __init__(self, *, session_daily_fetches: int, global_daily_fetches: int) -> None:
        super().__init__(
            session_limit=session_daily_fetches, global_limit=global_daily_fetches
        )


def _utc_day() -> date:
    return datetime.now(UTC).date()


def _next_reset() -> datetime:
    return datetime.combine(
        datetime.now(UTC).date() + timedelta(days=1), time(), tzinfo=UTC
    )
