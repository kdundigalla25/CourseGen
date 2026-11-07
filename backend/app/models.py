"""API contracts. Student state is returned to the browser, never persisted."""
from enum import StrEnum
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Issue(Model):
    id: str = ""
    code: str
    message: str
    page: int | None = None
    target_id: str | None = None
    review_required: bool = False


class ErrorDetail(Model):
    code: str
    message: str
    fields: list[str] = Field(default_factory=list)


class ErrorResponse(Model):
    error: ErrorDetail


class AttemptStatus(StrEnum):
    completed = "completed"
    in_progress = "in_progress"
    unknown = "unknown"


class Evidence(Model):
    page: int = Field(ge=1)
    line: int = Field(ge=1)
    text: str


class CourseAttempt(Model):
    id: str
    course_id: str | None = None
    raw_course_code: str = ""
    title: str = ""
    term: str | None = None
    grade: str | None = None
    credits: float | None = Field(default=None, ge=0)
    status: AttemptStatus = AttemptStatus.unknown
    origin: Literal["institution", "transfer", "exam", "unknown"] = "unknown"
    evidence: list[Evidence] = Field(default_factory=list)
    needs_review: bool = False


class RequirementAmount(Model):
    unit: Literal["courses", "credits", "gpa"]
    required: float | None = Field(default=None, ge=0)
    taken: float | None = Field(default=None, ge=0)
    needed: float | None = Field(default=None, ge=0)
    in_progress: float | None = Field(default=None, ge=0)


class AuditRequirement(Model):
    id: str
    parent_id: str | None = None
    label: str
    reported_status: Literal["satisfied", "not_satisfied", "unknown"] = "unknown"
    completion: Literal["completed", "in_progress", "mixed", "unknown"] = "unknown"
    rule_id: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    kind: Literal["group", "course", "elective", "policy", "non_course", "unknown"] = "unknown"
    attempt_ids: list[str] = Field(default_factory=list)
    amounts: list[RequirementAmount] = Field(default_factory=list)
    needs_review: bool = False


class CurriculumSelection(Model):
    starting_year: int | None = None
    entry_term: str | None = None
    reported_catalog_year: str | None = None
    gen_ed_version: str | None = None
    method: Literal["unresolved", "metadata", "requirements", "student_confirmed"] = "unresolved"
    candidate_versions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    program_terms: dict[str, str] = Field(default_factory=dict)


class ExtractedPage(Model):
    number: int
    text: str


class AuditDraft(Model):
    schema_version: Literal["1"] = "1"
    parser_version: Literal["tracker-0.2"] = "tracker-0.2"
    support: Literal["tracker_structure_detected", "unsupported"]
    review_state: Literal["extraction_only", "needs_review"] = "needs_review"
    page_count: int
    pages: list[ExtractedPage]
    curriculum: CurriculumSelection = Field(default_factory=CurriculumSelection)
    attempts: list[CourseAttempt] = Field(default_factory=list, max_length=500)
    requirements: list[AuditRequirement] = Field(default_factory=list, max_length=500)
    issues: list[Issue]


class ReviewRequest(Model):
    original: AuditDraft
    edited: AuditDraft
    acknowledged_issue_ids: list[str] = Field(default_factory=list)
    confirmed: bool = False


class ReviewChange(Model):
    field: str
    before: str | None
    after: str | None


class ReviewedAudit(Model):
    review_state: Literal["confirmed"] = "confirmed"
    revision: str
    audit: AuditDraft
    changes: list[ReviewChange]
    acknowledged_issue_ids: list[str]
    unresolved_issues: list[Issue]


class SourceSnapshot(Model):
    id: str
    source_url: str | None = None
    retrieved_at: str | None = None
    classification: Literal["public", "fictional"]
    edition: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    adapter_version: str | None = None


class Course(Model):
    id: str
    title: str
    credits_min: float = Field(ge=0, allow_inf_nan=False)
    credits_max: float = Field(ge=0, allow_inf_nan=False)
    source_snapshot_id: str
    prerequisite_text: str | None = None
    edition: str = "unversioned"
    description: str | None = None
    repeatable: bool = False

    @model_validator(mode="after")
    def valid_credits(self):
        if self.credits_max < self.credits_min:
            raise ValueError("Maximum credits must be at least minimum credits")
        return self


class Meeting(Model):
    kind: Literal["timed", "asynchronous", "arranged", "unknown"]
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_minute: int | None = Field(default=None, ge=0, lt=1440)
    end_minute: int | None = Field(default=None, gt=0, le=1440)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def valid_time(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Meeting date ranges require both dates")
        if self.start_date and self.end_date < self.start_date:
            raise ValueError("Meeting end date must not precede start date")
        if self.kind == "timed":
            if self.weekday is None or self.start_minute is None or self.end_minute is None:
                raise ValueError("Timed meetings require a day and both times")
            if self.start_minute >= self.end_minute:
                raise ValueError("Meeting end must follow start")
        elif any(v is not None for v in (self.weekday, self.start_minute, self.end_minute)):
            raise ValueError("Untimed meetings cannot contain fabricated times")
        return self


class Section(Model):
    id: str
    term_id: str
    course_id: str
    number: str
    source_snapshot_id: str
    meetings: list[Meeting]
    required_component_ids: list[str] = Field(default_factory=list)
    component: Literal["lecture", "lab", "recitation", "seminar", "other"] = "lecture"
    credit_value: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    instructor: str | None = None
    location: str | None = None
    modality: Literal["in_person", "online_synchronous", "asynchronous", "hybrid", "unknown"] = "unknown"
    linkage_status: Literal["verified", "not_required", "unknown"] = "unknown"
    crosslist_group_id: str | None = None
