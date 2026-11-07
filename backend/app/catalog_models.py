from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from app.models import Course, Model, Section, SourceSnapshot


class Term(Model):
    id: str
    name: str
    catalog_edition: str
    timezone: Literal['America/New_York'] = 'America/New_York'
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode='after')
    def dates(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError('Term date ranges need both dates')
        if self.start_date and self.end_date < self.start_date:
            raise ValueError('Term end must follow start')
        return self


class CourseDesignation(Model):
    course_id: str
    edition: str
    attribute_id: str
    source_snapshot_id: str
    section_id: str | None = None
    term_id: str | None = None

    @model_validator(mode='after')
    def section_scope(self):
        if (self.section_id is None) != (self.term_id is None):
            raise ValueError('Section-specific attributes require both section and term IDs')
        return self


class SectionBundle(Model):
    id: str
    term_id: str
    course_id: str
    section_ids: list[str] = Field(min_length=1)
    credits: float = Field(ge=0, allow_inf_nan=False)
    source_snapshot_id: str


class CatalogSnapshot(Model):
    schema_version: Literal['1'] = '1'
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    classification: Literal['fictional', 'public']
    description: str
    created_at: AwareDatetime
    sources: list[SourceSnapshot] = Field(min_length=1)
    courses: list[Course]
    designations: list[CourseDesignation] = Field(default_factory=list)
    terms: list[Term]
    sections: list[Section]
    bundles: list[SectionBundle]

    @model_validator(mode='after')
    def integrity(self):
        def indexed(items, key, label):
            result = {key(item): item for item in items}
            if len(result) != len(items):
                raise ValueError(f'Duplicate {label} IDs')
            return result
        sources = indexed(self.sources, lambda s: s.id, 'source')
        courses = indexed(self.courses, lambda c: (c.id, c.edition), 'course/edition')
        terms = indexed(self.terms, lambda t: t.id, 'term')
        sections = indexed(self.sections, lambda s: (s.term_id, s.id), 'section/term')
        indexed(self.bundles, lambda b: (b.term_id, b.id), 'bundle/term')
        for source in self.sources:
            if source.classification != self.classification:
                raise ValueError('Sample and public data cannot share one snapshot')
            if source.classification == 'public':
                if not source.source_url or not source.retrieved_at:
                    raise ValueError('Public sources require a URL and retrieval timestamp')
                HttpUrl(source.source_url)
                from pydantic import TypeAdapter
                TypeAdapter(AwareDatetime).validate_python(source.retrieved_at)
        for item in [*self.courses, *self.designations, *self.sections, *self.bundles]:
            if item.source_snapshot_id not in sources:
                raise ValueError('Record references an unknown source')
        for course in self.courses:
            if course.edition == 'unversioned':
                raise ValueError('Imported courses require an explicit catalog edition')
        for term in self.terms:
            if not any(edition == term.catalog_edition for _, edition in courses):
                raise ValueError('Term catalog edition has no course records')
        for section in self.sections:
            if section.term_id not in terms:
                raise ValueError('Section references an unknown term')
            term = terms[section.term_id]
            if (section.course_id, term.catalog_edition) not in courses:
                raise ValueError('Section references an unknown course edition')
            if section.modality == 'asynchronous' and any(m.kind == 'timed' for m in section.meetings):
                raise ValueError('Asynchronous sections cannot have fixed-time meetings')
            if not section.meetings:
                raise ValueError('Meetings must explicitly state timed, asynchronous, arranged or unknown')
            for meeting in section.meetings:
                if meeting.start_date and term.start_date and (meeting.start_date < term.start_date or meeting.end_date > term.end_date):
                    raise ValueError('Meeting date range falls outside the term')
            if len(set(section.required_component_ids)) != len(section.required_component_ids):
                raise ValueError('Duplicate required component IDs')
            for key in section.required_component_ids:
                other = sections.get((section.term_id, key))
                if not other or other.course_id != section.course_id or other.id == section.id:
                    raise ValueError('Linked components must exist in the same term/course and cannot reference themselves')
        designation_keys = [(d.course_id, d.edition, d.attribute_id, d.term_id, d.section_id) for d in self.designations]
        if len(set(designation_keys)) != len(designation_keys):
            raise ValueError('Duplicate designations')
        for designation in self.designations:
            if (designation.course_id, designation.edition) not in courses:
                raise ValueError('Designation references an unknown course edition')
            if designation.section_id:
                section = sections.get((designation.term_id, designation.section_id))
                if not section or section.course_id != designation.course_id or terms[designation.term_id].catalog_edition != designation.edition:
                    raise ValueError('Section designation has inconsistent course, term or edition')
        combinations = set()
        for bundle in self.bundles:
            term = terms.get(bundle.term_id)
            if not term or (bundle.course_id, term.catalog_edition) not in courses:
                raise ValueError('Bundle references an unknown term or course edition')
            chosen = set(bundle.section_ids)
            if len(chosen) != len(bundle.section_ids):
                raise ValueError('Bundle repeats a section')
            signature = (bundle.term_id, tuple(sorted(chosen)))
            if signature in combinations:
                raise ValueError('Duplicate bundle combination')
            combinations.add(signature)
            contribution = Decimal(0)
            for key in chosen:
                section = sections.get((bundle.term_id, key))
                if not section or section.course_id != bundle.course_id:
                    raise ValueError('Bundle sections must belong to its term and course')
                if not set(section.required_component_ids) <= chosen:
                    raise ValueError('Bundle omits a required linked component')
                if section.linkage_status == 'unknown':
                    raise ValueError('Bundles cannot assume unknown component linkage is valid')
                if section.credit_value is None:
                    raise ValueError('Bundle sections require explicit credit contributions')
                contribution += Decimal(str(section.credit_value))
            course = courses[(bundle.course_id, term.catalog_edition)]
            if Decimal(str(bundle.credits)) != contribution:
                raise ValueError('Bundle credits disagree with section credit contributions')
            if not course.credits_min <= bundle.credits <= course.credits_max:
                raise ValueError('Bundle credits fall outside the course credit range')
        return self


class AvailableTerm(Model):
    term: Term
    snapshot_id: str
    classification: Literal['fictional', 'public']
    notice: str
    sources: list[SourceSnapshot]


class CourseRecord(Model):
    course: Course
    designations: list[CourseDesignation]


class CourseSearchResult(Model):
    snapshot_id: str
    classification: Literal['fictional', 'public']
    notice: str
    total: int
    offset: int
    limit: int
    courses: list[CourseRecord]


class SectionOptions(Model):
    snapshot_id: str
    classification: Literal['fictional', 'public']
    notice: str
    course_id: str
    term_id: str
    sections: list[Section]
    bundles: list[SectionBundle]
    sources: list[SourceSnapshot]
