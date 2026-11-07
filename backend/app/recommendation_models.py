from typing import Literal

from app.models import Evidence, Model, RequirementAmount, ReviewedAudit, SourceSnapshot
from app.rule_models import CurriculumResolution, RuleSource


class RecommendationRequest(Model):
    reviewed: ReviewedAudit
    snapshot_id: str
    term_id: str


class RequirementMatch(Model):
    requirement_id: str
    label: str
    pack_id: str
    rule_id: str
    match_type: Literal['direct_course', 'attribute']
    explanation: str
    qualifying_bundle_ids: list[str]
    section_options: list[str]
    audit_evidence: list[Evidence]
    sources: list[RuleSource]
    notes: list[str]


class CourseSuggestion(Model):
    course_id: str
    edition: str
    title: str | None
    credits_min: float | None
    credits_max: float | None
    availability: Literal['available', 'not_offered', 'missing_catalog', 'unknown_meetings', 'no_qualifying_sections']
    selectable: bool
    eligibility: Literal['unverified', 'conditional'] = 'unverified'
    prerequisite_text: str | None = None
    warnings: list[str]
    matches: list[RequirementMatch]


class ManualRequirement(Model):
    requirement_id: str
    label: str
    reason: Literal['status_unknown', 'non_course', 'policy_or_elective', 'unmapped', 'ambiguous_mapping', 'no_available_candidate', 'curriculum_unresolved']
    message: str
    amounts: list[RequirementAmount]
    evidence: list[Evidence]


class ExcludedCourse(Model):
    requirement_id: str
    course_id: str
    reason: Literal['completed', 'in_progress']
    message: str


class RecommendationResult(Model):
    audit_revision: str
    snapshot_id: str
    snapshot_digest: str
    term_id: str
    classification: Literal['fictional', 'public']
    notice: str
    sources: list[SourceSnapshot]
    resolution: CurriculumResolution
    suggestions: list[CourseSuggestion]
    manual_requirements: list[ManualRequirement]
    excluded_courses: list[ExcludedCourse]
    counting_notice: str
    warnings: list[str]
