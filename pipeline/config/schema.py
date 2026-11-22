"""Pydantic schemas for the files in `config/`.

The YAML files are the source of truth for key names; these models codify them.
See docs/DESIGN.md §3.1 (data model), §4 (topic modes) and §10.3 (private profile).
Every model forbids unknown keys so a typo fails validation instead of being ignored.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
FilterName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]

Mode = Literal[
    "threaded", "flat", "tracker", "question", "patch_cycle", "fixed", "listings", "reading_list"
]
Credibility = Literal["beta_confirmed", "reputable_leaker", "unverified", "fake"]
ProfileSection = Literal["gear", "health", "jobs"]
Lean = Literal["left", "center-left", "center", "center-right", "right"]
ContentKind = Literal["reporting", "analysis", "opinion", "study", "listing", "guide"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ───────────────────────────── topics.yaml ─────────────────────────────


class Defaults(StrictModel):
    daily_cap_per_thread: PositiveInt
    dormant_after_days: PositiveInt
    archive_after_days: PositiveInt
    lookback_days: PositiveInt


class Group(StrictModel):
    id: Id
    name: NonEmptyStr


class FixedThread(StrictModel):
    """A predefined thread for `tracker` and `fixed` topics."""

    id: Id
    title: NonEmptyStr
    priority: Literal["low", "normal"] = "normal"


class CycleThread(StrictModel):
    """One of the per-version threads of a `patch_cycle` topic."""

    id: Id
    title: NonEmptyStr
    accepts: list[Credibility] = Field(min_length=1)
    label: str | None = None


class OpinionPolicy(StrictModel):
    allowed: bool = False
    label: bool = True
    balance_across_lean: bool = False


_CAP_FIELDS = ("max_per_day", "max_per_week", "max_per_month", "target_per_week")


class Topic(StrictModel):
    id: Id
    name: NonEmptyStr
    group: Id
    mode: Mode
    description: NonEmptyStr
    include: list[NonEmptyStr] = []
    exclude: list[NonEmptyStr] = []
    filters_off: list[FilterName] = []

    # Overrides of `defaults`
    daily_cap_per_thread: PositiveInt | None = None
    dormant_after_days: PositiveInt | None = None
    archive_after_days: PositiveInt | None = None
    lookback_days: PositiveInt | None = None

    # Caps
    max_per_day: PositiveInt | None = None
    max_per_week: PositiveInt | None = None
    max_per_month: PositiveInt | None = None
    target_per_week: PositiveInt | None = None

    # Predefined threads
    threads: list[FixedThread] | None = None
    threads_per_cycle: list[CycleThread] | None = None

    # Private-profile matching
    compare_with_profile: ProfileSection | None = None
    match_profile: ProfileSection | None = None

    # Genshin / spoiler handling
    spoiler_policy: Literal["fail_closed"] | None = None
    images: bool = True
    hide_credibility: list[Credibility] = []
    known_leakers: list[NonEmptyStr] = []

    # Health
    evidence: Literal["studies_preferred"] | None = None
    study_cards: bool = False

    # News
    primers: bool = False
    opinion: OpinionPolicy | None = None
    weekly_region_roundup: bool = False
    regions: list[NonEmptyStr] = []

    # Markets
    advice: Literal["never"] | None = None

    @model_validator(mode="after")
    def _mode_rules(self) -> Topic:
        if self.mode in ("tracker", "fixed"):
            if not self.threads:
                raise ValueError(f"mode '{self.mode}' requires a non-empty `threads` list")
        elif self.threads is not None:
            raise ValueError("`threads` is only allowed for modes 'tracker' and 'fixed'")

        if self.mode == "patch_cycle":
            if not self.threads_per_cycle:
                raise ValueError("mode 'patch_cycle' requires a non-empty `threads_per_cycle`")
        elif self.threads_per_cycle is not None:
            raise ValueError("`threads_per_cycle` is only allowed for mode 'patch_cycle'")

        if self.mode in ("flat", "reading_list") and all(
            getattr(self, f) is None for f in _CAP_FIELDS
        ):
            raise ValueError(f"mode '{self.mode}' requires a cap ({', '.join(_CAP_FIELDS[:3])})")

        if self.mode == "listings" and self.target_per_week is None:
            raise ValueError("mode 'listings' requires `target_per_week`")

        thread_ids = [t.id for t in (self.threads or self.threads_per_cycle or [])]
        if dupes := duplicates(thread_ids):
            raise ValueError(f"duplicate thread ids: {', '.join(dupes)}")
        return self


class TopicsFile(StrictModel):
    defaults: Defaults
    groups: list[Group] = Field(min_length=1)
    global_filters: dict[FilterName, NonEmptyStr] = {}
    topics: list[Topic] = Field(min_length=1)


# ───────────────────────────── sources.yaml ─────────────────────────────


class Source(StrictModel):
    id: Id
    type: Literal["rss", "reddit"]
    url: HttpUrl | None = None
    subreddit: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{2,21}$")] | None = None
    topics: list[Id] = Field(min_length=1)
    status: Literal["active", "trial", "disabled"]
    weight: Annotated[float, Field(ge=0.5, le=1.5)] = 1.0
    lean: Lean | None = None
    kind: ContentKind | None = None
    verified: bool = False
    options: dict[str, Any] = {}

    @model_validator(mode="after")
    def _type_rules(self) -> Source:
        if self.type == "rss":
            if self.url is None:
                raise ValueError("rss sources require `url`")
            if self.subreddit is not None:
                raise ValueError("rss sources must not set `subreddit`")
        elif self.type == "reddit":
            if self.subreddit is None:
                raise ValueError("reddit sources require `subreddit`")
            if self.url is not None:
                raise ValueError("reddit sources must not set `url` (use `subreddit`)")
        return self


class SourcesFile(StrictModel):
    sources: list[Source] = Field(min_length=1)


# ───────────────────────────── profile.yaml (private) ─────────────────────────────


class PrivateModel(StrictModel):
    # Validation errors never echo input values: this file holds personal data.
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class HealthProfile(PrivateModel):
    goals: list[str] = []
    notes: str | None = None


class JobConstraints(PrivateModel):
    work_authorization: str | None = None
    clearance_ok: bool = False


class JobsProfile(PrivateModel):
    seeking: list[Literal["internship", "new_grad"]] = Field(min_length=1)
    role_families: list[NonEmptyStr] = []
    industries: Literal["any"] | list[NonEmptyStr] = "any"
    skills_summary: str | None = None
    locations: list[NonEmptyStr] = ["any"]
    constraints: JobConstraints = JobConstraints()
    pause_listings_until: dt.date | None = None


class Profile(PrivateModel):
    """Every section is optional so a forker can omit what they don't use."""

    gear: dict[str, str | None] = {}
    health: HealthProfile | None = None
    jobs: JobsProfile | None = None


# ───────────────────────────── helpers ─────────────────────────────


def duplicates(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for i in ids:
        if i in seen and i not in dupes:
            dupes.append(i)
        seen.add(i)
    return dupes
