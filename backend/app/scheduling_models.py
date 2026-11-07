from typing import Literal

from pydantic import Field, model_validator

from app.models import Model, ReviewedAudit, Section, SourceSnapshot


class SchedulingSelection(Model):
    course_id: str
    required: bool = False
    source: Literal['suggestion', 'manual'] = 'manual'
    requirement_ids: list[str] = Field(default_factory=list)


class SchedulePreferences(Model):
    minimum_credits: float = Field(default=3, ge=0, le=30, allow_inf_nan=False)
    maximum_credits: float = Field(default=18, ge=0, le=30, allow_inf_nan=False)
    target_credits: float = Field(default=12, ge=0, le=30, allow_inf_nan=False)
    earliest_start: int = Field(default=480, ge=0, lt=1440)
    latest_end: int = Field(default=1260, gt=0, le=1440)
    avoided_days: list[int] = Field(default_factory=list)
    preferred_time: Literal['none', 'morning', 'afternoon'] = 'none'
    compact_days: bool = False

    @model_validator(mode='after')
    def consistent(self):
        if not self.minimum_credits <= self.target_credits <= self.maximum_credits:
            raise ValueError('Minimum, target and maximum credits must be in order')
        if self.earliest_start >= self.latest_end:
            raise ValueError('Earliest start must be before latest end')
        if any(day < 0 or day > 6 for day in self.avoided_days) or len(set(self.avoided_days)) != len(self.avoided_days):
            raise ValueError('Avoided days must be unique weekdays from 0 through 6')
        return self


class ScheduleRequest(Model):
    reviewed: ReviewedAudit
    snapshot_id: str
    term_id: str
    selections: list[SchedulingSelection] = Field(min_length=1, max_length=12)
    preferences: SchedulePreferences = Field(default_factory=SchedulePreferences)
    rule_revisions: dict[str, str] | None = None
    expected_snapshot_digest: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    result_limit: int = Field(default=10, ge=1, le=20)
    node_budget: int = Field(default=100000, ge=1, le=200000)


class ScheduleDiagnostic(Model):
    code: str
    message: str
    course_ids: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ScheduledCourse(Model):
    course_id: str
    title: str
    bundle_id: str
    credits: float
    sections: list[Section]
    source: Literal['suggestion', 'manual']
    possible_requirement_ids: list[str]
    possible_requirement_labels: list[str]


class CandidateSchedule(Model):
    id: str
    courses: list[ScheduledCourse]
    total_credits: float
    score: float
    score_breakdown: dict[str, float]
    reasons: list[str]


class FilteredCourse(Model):
    course_id: str
    available_bundles: int
    rejected_reasons: dict[str, int]


class ScheduleResult(Model):
    audit_revision: str
    snapshot_id: str
    snapshot_digest: str
    term_id: str
    timezone: str
    classification: Literal['fictional', 'public']
    notice: str
    sources: list[SourceSnapshot]
    rule_revisions: dict[str, str]
    schedules: list[CandidateSchedule]
    search_complete: bool
    nodes_visited: int
    feasible_schedules_found: int
    filtered_courses: list[FilteredCourse]
    diagnostics: list[ScheduleDiagnostic]
    warnings: list[str]
