"""Stateless review validation and revision tracking; no server-side student store."""
import hashlib
import json
import re

from app.audit_parser import TERM, update_completion
from app.models import AuditDraft, Issue, ReviewChange, ReviewedAudit, ReviewRequest


class InvalidReview(ValueError):
    def __init__(self, message: str, fields: list[str] | None = None, code: str = 'invalid_review'):
        self.message = message
        self.fields = fields or []
        self.code = code


def validate_reviewed(reviewed: ReviewedAudit) -> None:
    validate_audit(reviewed.audit)
    revision = hashlib.sha256(reviewed.audit.model_dump_json().encode()).hexdigest()[:24]
    if reviewed.revision != revision:
        raise InvalidReview('Your details changed after confirmation. Review and confirm them again.', code='stale_review')


def validate_audit(audit: AuditDraft) -> None:
    curriculum = audit.curriculum
    if curriculum.starting_year is not None and not 1900 <= curriculum.starting_year <= 2100:
        raise InvalidReview("Starting year must be between 1900 and 2100.", ["curriculum.starting_year"])
    if curriculum.entry_term:
        if not re.fullmatch(TERM, curriculum.entry_term):
            raise InvalidReview("Use a starting term such as 2024 Fall or 2025 Spr.", ["curriculum.entry_term"])
        if curriculum.starting_year is not None and int(curriculum.entry_term[:4]) != curriculum.starting_year:
            raise InvalidReview("Starting year and entry term must agree.", ["curriculum.starting_year", "curriculum.entry_term"])
    if curriculum.reported_catalog_year:
        match = re.fullmatch(r"(\d{4})-(\d{4})", curriculum.reported_catalog_year)
        if not match or int(match[2]) != int(match[1]) + 1:
            raise InvalidReview("Use a catalog year such as 2024-2025.", ["curriculum.reported_catalog_year"])
    for name, term in curriculum.program_terms.items():
        if not name.strip() or not re.fullmatch(TERM, term):
            raise InvalidReview("Each program needs a name and a valid requirement term.", ["curriculum.program_terms"])
    attempts = {attempt.id for attempt in audit.attempts}
    requirements = {requirement.id: requirement for requirement in audit.requirements}
    if len(attempts) != len(audit.attempts) or len(requirements) != len(audit.requirements):
        raise InvalidReview("Course attempt and requirement IDs must be unique.")
    for attempt in audit.attempts:
        if not attempt.id.strip() or not (attempt.course_id or attempt.raw_course_code.strip() or attempt.title.strip()):
            raise InvalidReview("Each course record needs a code or descriptive title.", [f"attempts.{attempt.id}"])
        if attempt.course_id and not re.fullmatch(r"[A-Z]{2,5} \d{1,3}[A-Z]*", attempt.course_id):
            raise InvalidReview("Course codes must use a subject and number, such as COMP 210.", [f"attempts.{attempt.id}.course_id"])
        if attempt.term and not re.fullmatch(TERM, attempt.term):
            raise InvalidReview("Course terms must use a year and semester.", [f"attempts.{attempt.id}.term"])
    for requirement in audit.requirements:
        if not requirement.id.strip() or not requirement.label.strip():
            raise InvalidReview("Each requirement needs a description.", [f"requirements.{requirement.id}.label"])
        if not set(requirement.attempt_ids) <= attempts:
            raise InvalidReview("A requirement references a missing course record.", [f"requirements.{requirement.id}.attempt_ids"])
        ancestor = requirement.parent_id
        seen = {requirement.id}
        while ancestor:
            if ancestor not in requirements or ancestor in seen:
                raise InvalidReview("Requirement groups must reference existing parents without cycles.", [f"requirements.{requirement.id}.parent_id"])
            seen.add(ancestor)
            ancestor = requirements[ancestor].parent_id


def review(request: ReviewRequest) -> ReviewedAudit:
    if not request.confirmed:
        raise InvalidReview("Confirm that you have reviewed the extracted records before continuing.", ["confirmed"])
    required = {issue.id for issue in request.original.issues if issue.review_required}
    acknowledged = set(request.acknowledged_issue_ids)
    if not required <= acknowledged:
        raise InvalidReview("Review and acknowledge the flagged items before confirming.", ["acknowledged_issue_ids"])
    edited = request.edited.model_copy(deep=True)
    # Extracted evidence/support and parser issues are not editable fulfillment claims.
    edited.pages = request.original.pages
    edited.page_count = request.original.page_count
    edited.support = request.original.support
    edited.issues = [issue.model_copy(deep=True) for issue in request.original.issues]
    edited.curriculum.gen_ed_version = None
    edited.curriculum.candidate_versions = []
    edited.curriculum.method = "unresolved"
    for requirement in edited.requirements:
        requirement.rule_id = None
    validate_audit(edited)
    update_completion(edited)
    changes: list[ReviewChange] = []

    def record(path: str, before, after):
        if before != after:
            changes.append(ReviewChange(field=path,
                before=None if before is None else json.dumps(before, sort_keys=True, ensure_ascii=False),
                after=None if after is None else json.dumps(after, sort_keys=True, ensure_ascii=False)))

    original = request.original
    for name in ("starting_year", "entry_term", "reported_catalog_year", "program_terms"):
        record(f"curriculum.{name}", getattr(original.curriculum, name), getattr(edited.curriculum, name))
    for field in ("attempts", "requirements"):
        previous = {item.id: item.model_dump(mode="json", exclude={"evidence"}) for item in getattr(original, field)}
        current = {item.id: item.model_dump(mode="json", exclude={"evidence"}) for item in getattr(edited, field)}
        for identity in sorted(previous.keys() | current.keys()):
            record(f"{field}.{identity}", previous.get(identity), current.get(identity))
    remaining = []
    attempts = {item.id: item for item in edited.attempts}
    requirements = {item.id: item for item in edited.requirements}
    for issue in original.issues:
        if not issue.review_required:
            continue
        attempt = attempts.get(issue.target_id)
        requirement = requirements.get(issue.target_id)
        if issue.target_id and not attempt and not requirement:
            continue
        if issue.code == "unknown_attempt_status" and attempt and attempt.status != "unknown":
            continue
        if issue.code == "incomplete_course_row" and attempt and attempt.term and attempt.credits is not None:
            continue
        if issue.code == "non_catalog_credit" and attempt and attempt.course_id:
            continue
        if issue.code == "unknown_requirement_status" and requirement and requirement.reported_status != "unknown":
            continue
        if issue.code in {"missing_entry_term", "conflicting_entry_terms"} and edited.curriculum.entry_term:
            continue
        if issue.code == "conflicting_catalog_years" and edited.curriculum.reported_catalog_year:
            continue
        remaining.append(issue)

    def unresolved(code: str, message: str, target: str | None = None):
        if not any(item.code == code and item.target_id == target for item in remaining):
            item = Issue(id=f"review-{code}-{target or 'metadata'}", code=code, message=message, target_id=target, review_required=True)
            remaining.append(item)
            edited.issues.append(item)

    for attempt in edited.attempts:
        if attempt.status == "unknown":
            unresolved("unknown_attempt_status", "This reviewed course record still has an unknown status.", attempt.id)
        if not attempt.course_id:
            unresolved("non_catalog_credit", "This reviewed credit record has no selectable course code.", attempt.id)
        if not attempt.term or attempt.credits is None:
            unresolved("incomplete_course_row", "This reviewed record is missing its term or credit value.", attempt.id)
    for requirement in edited.requirements:
        if requirement.reported_status == "unknown":
            unresolved("unknown_requirement_status", "This reviewed requirement still has an unknown reported status.", requirement.id)
    if edited.curriculum.starting_year and edited.curriculum.reported_catalog_year and not edited.curriculum.reported_catalog_year.startswith(str(edited.curriculum.starting_year)):
        unresolved("entry_catalog_disagreement", "The reviewed starting year and catalog label differ; Gen Ed applicability remains unresolved.")
    for attempt in edited.attempts:
        attempt.needs_review = attempt.status == "unknown" or not attempt.course_id or not attempt.term or attempt.credits is None or any(item.target_id == attempt.id for item in remaining)
    for requirement in edited.requirements:
        requirement.needs_review = requirement.reported_status == "unknown" or any(item.target_id == requirement.id for item in remaining)
    revision = hashlib.sha256(edited.model_dump_json().encode()).hexdigest()[:24]
    return ReviewedAudit(revision=revision, audit=edited, changes=changes,
        acknowledged_issue_ids=sorted(acknowledged & {issue.id for issue in original.issues}),
        unresolved_issues=remaining)
