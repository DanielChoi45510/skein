"""Pydantic schemas for the files in `config/`.

The YAML files are the source of truth for key names; these models codify them.
See docs/DESIGN.md §3.1 (data model), §4 (topic modes) and §10.3 (private profile).
Every model forbids unknown keys so a typo fails validation instead of being ignored.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
FilterName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]

Mode = Literal[
    "threaded", "flat", "tracker", "question", "patch_cycle", "fixed", "listings", "reading_list"
]
Credibility = Literal["beta_confirmed", "reputable_leaker", "unverified", "fake"]
ProfileSection = Literal["gear", "health", "jobs"]
Lean = Literal["left", "lean_left", "center", "lean_right", "right"]  # AllSides scale
ContentKind = Literal["reporting", "analysis", "opinion", "study", "listing", "guide"]
LEAN_KINDS = frozenset({"reporting", "analysis", "opinion"})  # kinds an outlet lean applies to
Paywall = Literal["none", "partial", "full"]
# Source types whose fetchers arrive in Phase 4. Until then they must stay disabled.
FUTURE_SOURCE_TYPES = frozenset({"github_list", "nyt_books", "fred"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ───────────────────────────── topics.yaml ─────────────────────────────


class StructureParams(StrictModel):
    """Thread structure for the spine-and-branches view (DESIGN §6.9).

    Picked from the stored data on 2026-11-24; see docs/overnight-log.md.
    """

    link: Fraction  # storylines: merge while their average pairwise cosine is ≥ this
    link_predefined: Fraction  # the same for tracker / fixed threads (broad by design)
    min_items: PositiveInt  # threads smaller than this are all spine
    min_branch_items: PositiveInt  # smaller storylines fold into the spine instead of branching
    min_branch_items_predefined: PositiveInt  # the same for tracker / fixed threads
    anchor_day_penalty: Annotated[float, Field(ge=0.0, le=1.0)]  # per day, when anchoring a branch
    related: Fraction  # related threads: thread-centroid cosine ≥ this
    related_max: Annotated[int, Field(ge=0, le=20)]


class Defaults(StrictModel):
    daily_cap_per_thread: PositiveInt
    cooling_after_days: PositiveInt  # thread lifecycle (DESIGN §5): active → cooling
    dormant_after_days: PositiveInt
    archive_after_days: PositiveInt
    lookback_days: PositiveInt
    relevance_threshold: Fraction  # items scoring below this for every topic are hidden
    structure: StructureParams


class Group(StrictModel):
    id: Id
    name: NonEmptyStr


class FixedThread(StrictModel):
    """A predefined thread for `tracker` and `fixed` topics.

    Items go to the nearest thread by similarity to `description` (else the
    title). A bare title like "Phones" makes a weak anchor (DESIGN §6.5).
    """

    id: Id
    title: NonEmptyStr
    description: NonEmptyStr | None = None
    priority: Literal["low", "normal"] = "normal"
    # The topic's catch-all: never matched by its own description; it gets the
    # items whose best match among the other threads is below the topic's
    # `min_match` (DESIGN §6.5). At most one per topic, and only with `min_match`.
    catch_all: bool = False


class CycleThread(StrictModel):
    """One of the per-version threads of a `patch_cycle` topic."""

    id: Id
    title: NonEmptyStr
    accepts: list[Credibility] = Field(min_length=1)
    label: str | None = None


class Panel(StrictModel):
    """A data panel shown above a topic (Markets: index closes, DESIGN §8.9). Phase 4."""

    provider: Literal["fred"]
    series: list[NonEmptyStr] = Field(min_length=1)


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
    cooling_after_days: PositiveInt | None = None
    dormant_after_days: PositiveInt | None = None
    archive_after_days: PositiveInt | None = None
    lookback_days: PositiveInt | None = None
    relevance_threshold: Fraction | None = None

    # Caps
    max_per_day: PositiveInt | None = None
    max_per_week: PositiveInt | None = None
    max_per_month: PositiveInt | None = None
    target_per_week: PositiveInt | None = None

    # Predefined threads
    threads: list[FixedThread] | None = None
    # Tracker / fixed: an item whose best thread scores below this goes to the
    # topic's `catch_all` thread instead of being forced into the nearest one.
    min_match: Fraction | None = None
    threads_per_cycle: list[CycleThread] | None = None

    # Private-profile matching
    compare_with_profile: ProfileSection | None = None
    match_profile: ProfileSection | None = None

    # Spoiler / credibility handling (no topic uses it today; see DESIGN "Parked")
    spoiler_policy: Literal["fail_closed"] | None = None
    images: bool = True
    hide_credibility: list[Credibility] = []
    known_leakers: list[NonEmptyStr] = []

    # Health
    evidence: Literal["articles_about_studies"] | None = None
    study_cards: bool = False

    # News
    primers: bool = False
    opinion: OpinionPolicy | None = None
    weekly_region_roundup: bool = False
    regions: list[NonEmptyStr] = []

    # Markets
    advice: Literal["never"] | None = None
    panel: Panel | None = None

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

        catch_alls = [t.id for t in self.threads or [] if t.catch_all]
        if len(catch_alls) > 1:
            raise ValueError(f"at most one `catch_all` thread, got: {', '.join(catch_alls)}")
        if (self.min_match is None) != (not catch_alls):
            raise ValueError(
                "`min_match` and a `catch_all` thread go together: set both or neither"
            )
        if catch_alls and len(self.threads or []) < 2:
            raise ValueError("a `catch_all` thread needs at least one other thread to match")

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


class SourceRelevance(StrictModel):
    """Per-source relevance override: a different bar, or never hidden (`skip`).

    Skipped sources are still scored, so ranking uses real relevance.
    """

    threshold: Fraction | None = None
    skip: bool = False

    @model_validator(mode="after")
    def _one_of(self) -> SourceRelevance:
        if self.skip == (self.threshold is not None):
            raise ValueError("set exactly one of `threshold` or `skip: true`")
        return self


class Source(StrictModel):
    id: Id
    name: NonEmptyStr | None = None  # display name; else the feed's own title, else the id
    type: Literal["rss", "reddit", "github_list", "nyt_books", "fred"]
    url: HttpUrl | None = None
    subreddit: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{2,21}$")] | None = None
    topics: list[Id] = Field(min_length=1)
    status: Literal["active", "trial", "disabled"]
    weight: Annotated[float, Field(ge=0.5, le=1.5)] = 1.0
    lean: Lean | None = None  # only with kind reporting / analysis / opinion
    kind: ContentKind | None = None
    paywall: Paywall = "none"  # partial / full: lock badge on cards
    verified: bool = False
    excerpt: bool = True  # false: drop the feed's description (e.g. when it's boilerplate)
    # false: never show the image the feed offers (CLAUDE.md principle 3). Images are
    # only ever loaded from the source's URL, never downloaded or re-hosted.
    images: bool = True
    relevance: SourceRelevance | None = None
    # Regexes (case-insensitive, re.search): entries whose title matches are dropped,
    # and stored ones hidden, e.g. stock-quote pages in a search feed (DESIGN §6.2).
    title_exclude: list[NonEmptyStr] = []
    # Regexes (case-insensitive) whose matches are removed from titles, e.g. a
    # " - Reuters" suffix the card already shows as the source. After title_exclude.
    title_strip: list[NonEmptyStr] = []
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
        else:  # Phase 4 types: settings live in `options`
            if self.url is not None or self.subreddit is not None:
                raise ValueError(f"{self.type} sources take no `url`/`subreddit` (use `options`)")
            if self.status != "disabled":
                raise ValueError(
                    f"{self.type} sources must stay `status: disabled` until their fetcher "
                    "exists (DESIGN §14 phase 4)"
                )
        if self.lean is not None and self.kind not in LEAN_KINDS:
            raise ValueError("`lean` is only allowed with kind reporting, analysis or opinion")
        for key in ("title_exclude", "title_strip"):
            for n, pattern in enumerate(getattr(self, key)):
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"{key}[{n}] is not a valid regex: {e}") from e
        if self.relevance and self.relevance.skip and len(self.topics) != 1:
            raise ValueError("`relevance: {skip: true}` needs exactly one topic to route items to")
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


THREADED_MODES = frozenset({"threaded", "question", "tracker", "fixed"})  # DESIGN §6.5
PREDEFINED_MODES = frozenset({"tracker", "fixed"})  # only the threads listed in config


@dataclass(frozen=True)
class Lifecycle:
    """A topic's effective thread timings in days (DESIGN §5): topic override, else default."""

    cooling: int
    dormant: int
    archive: int


LIFECYCLE_FIELDS = ("cooling_after_days", "dormant_after_days", "archive_after_days")


def lifecycle(topic: Topic, defaults: Defaults) -> Lifecycle | None:
    """None for tracker and fixed topics: their threads never cool, go dormant or archive."""
    if topic.mode in PREDEFINED_MODES:
        return None
    return Lifecycle(
        cooling=topic.cooling_after_days or defaults.cooling_after_days,
        dormant=topic.dormant_after_days or defaults.dormant_after_days,
        archive=topic.archive_after_days or defaults.archive_after_days,
    )


def duplicates(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for i in ids:
        if i in seen and i not in dupes:
            dupes.append(i)
        seen.add(i)
    return dupes
