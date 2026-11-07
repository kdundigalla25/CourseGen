"""Versioned, sourced category definitions; these are not a degree evaluator."""
from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.models import Model


class RuleSource(Model):
    id: str
    url: HttpUrl
    edition: str
    locator: str
    verified_on: date
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RequirementDefinition(Model):
    id: str
    label: str
    group: str
    kind: Literal["course", "attribute", "any_of", "all_of", "policy", "non_course"]
    audit_labels: list[str] = Field(min_length=1)
    course_ids: list[str] = Field(default_factory=list)
    attribute_ids: list[str] = Field(default_factory=list)
    child_ids: list[str] = Field(default_factory=list)
    minimum_courses: int | None = Field(default=None, ge=0)
    minimum_credits: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    minimum_grade: str | None = None
    source_ids: list[str] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)
    support: Literal["candidate_matching", "manual"] = "manual"


class CountingPolicy(Model):
    id: str
    kind: Literal["one_focus_per_course", "exclusive", "exam_focus_limit", "manual"]
    requirement_ids: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=0)
    description: str
    source_ids: list[str] = Field(min_length=1)
    enforcement: Literal["not_evaluated"] = "not_evaluated"


class RulePack(Model):
    schema_version: Literal["1"] = "1"
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    revision: str
    coverage: Literal["partial"] = "partial"
    sources: list[RuleSource] = Field(min_length=1)
    requirements: list[RequirementDefinition] = Field(min_length=1)
    policies: list[CountingPolicy] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_references(self):
        sources = {source.id for source in self.sources}
        rules = {rule.id: rule for rule in self.requirements}
        if len(sources) != len(self.sources) or len(rules) != len(self.requirements):
            raise ValueError("Source and requirement IDs must be unique within a pack")
        for item in [*self.requirements, *self.policies]:
            if not set(item.source_ids) <= sources:
                raise ValueError("Rules and policies must reference known sources")
        for rule in self.requirements:
            if not set(rule.child_ids) <= rules.keys():
                raise ValueError("Rule references an unknown child")
            if rule.kind == 'course' and not rule.course_ids:
                raise ValueError("Course rules need qualifying course IDs")
            if rule.kind == 'attribute' and not rule.attribute_ids:
                raise ValueError("Attribute rules need qualifying attributes")
        for policy in self.policies:
            if not set(policy.requirement_ids) <= rules.keys():
                raise ValueError("Counting policy references an unknown requirement")
        def visit(key, ancestors):
            if key in ancestors:
                raise ValueError("Requirement rule hierarchy contains a cycle")
            for child in rules[key].child_ids:
                visit(child, ancestors | {key})
        for key in rules:
            visit(key, set())
        return self


class GenEdRulePack(RulePack):
    scope: Literal["gen_ed"] = "gen_ed"
    family: Literal["ideas_in_action"] = "ideas_in_action"
    cohort_year: int = Field(ge=1900, le=2100)
    catalog_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    signature_rule_ids: list[str] = Field(min_length=1)
    # Explicitly includes cohorts that may not yet have a loaded rule pack.
    # A unique match among installed packs does not prove a unique starting year.
    signature_cohort_years: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_cohort(self):
        if self.catalog_year != f"{self.cohort_year}-{self.cohort_year + 1}":
            raise ValueError("Catalog edition and cohort year disagree")
        if not set(self.signature_rule_ids) <= {r.id for r in self.requirements}:
            raise ValueError("Signature references unknown requirements")
        if self.cohort_year not in self.signature_cohort_years:
            raise ValueError("Signature must include its own cohort")
        return self


class ProgramRulePack(RulePack):
    scope: Literal["program"] = "program"
    program_id: str
    program_name: str
    audit_program_names: list[str] = Field(min_length=1)
    requirement_term: str = Field(pattern=r'^\d{4} (Fall|Spr|Spring|SumI|SumII|Summer)$')


class SelectionEvidence(Model):
    kind: Literal["entry_term", "starting_year", "catalog_label", "requirement_signature", "program_term"]
    value: str


class ProgramSelection(Model):
    name: str
    requirement_term: str
    pack_id: str | None = None
    state: Literal["selected", "unsupported"]


class CurriculumResolution(Model):
    state: Literal["selected", "ambiguous", "conflict", "unsupported"]
    gen_ed_version: str | None = None
    method: Literal["metadata", "requirements", "unresolved"] = "unresolved"
    candidate_versions: list[str]
    unsupported_cohort_years: list[int]
    evidence: list[SelectionEvidence]
    programs: list[ProgramSelection]
    warnings: list[str]
    rule_revisions: dict[str, str]
    coverage: Literal["partial"] = "partial"


class AvailableCurricula(Model):
    gen_ed: list[GenEdRulePack]
    programs: list[ProgramRulePack]
