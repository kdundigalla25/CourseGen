from pathlib import Path

from app.catalog_models import AvailableTerm, CatalogSnapshot, CourseRecord, CourseSearchResult, SectionOptions
from app.curriculum import DATA_ROOT


def notice(snapshot: CatalogSnapshot) -> str:
    return 'Fictional sample data. Not official UNC offerings.' if snapshot.classification == 'fictional' else 'Imported public data. Check the source and retrieval time; seat availability is not live.'


def load_catalogs(root: Path = DATA_ROOT) -> list[CatalogSnapshot]:
    found: dict[str, CatalogSnapshot] = {}
    for folder in ('samples', 'published'):
        for path in sorted((root / folder).glob('*.json')):
            snapshot = CatalogSnapshot.model_validate_json(path.read_text(encoding='utf-8'))
            if snapshot.id in found and snapshot != found[snapshot.id]:
                raise ValueError('Conflicting catalog snapshot IDs')
            found[snapshot.id] = snapshot
    return sorted(found.values(), key=lambda snapshot: snapshot.id)


def find_snapshot(identity: str, root: Path = DATA_ROOT) -> CatalogSnapshot:
    for snapshot in load_catalogs(root):
        if snapshot.id == identity:
            return snapshot
    raise LookupError('Unknown dataset. Select an available snapshot.')


def available_terms(root: Path = DATA_ROOT) -> list[AvailableTerm]:
    return [AvailableTerm(term=term, snapshot_id=snapshot.id, classification=snapshot.classification,
                          notice=notice(snapshot), sources=snapshot.sources)
            for snapshot in load_catalogs(root) for term in snapshot.terms]


def search_courses(snapshot: CatalogSnapshot, *, query: str = '', term_id: str | None = None,
                   attribute_id: str | None = None, offset: int = 0, limit: int = 30) -> CourseSearchResult:
    term = next((item for item in snapshot.terms if item.id == term_id), None)
    if term_id and term is None:
        raise LookupError('Unknown term in this dataset.')
    courses = []
    for course in sorted(snapshot.courses, key=lambda c: (c.id, c.edition)):
        if query.casefold() not in f'{course.id} {course.title}'.casefold():
            continue
        if term and (course.edition != term.catalog_edition or not any(s.term_id == term.id and s.course_id == course.id for s in snapshot.sections)):
            continue
        designations = [d for d in snapshot.designations if d.course_id == course.id and d.edition == course.edition and (d.term_id is None or (term and d.term_id == term.id))]
        if attribute_id and not any(d.attribute_id == attribute_id for d in designations):
            continue
        courses.append(CourseRecord(course=course, designations=designations))
    return CourseSearchResult(snapshot_id=snapshot.id, classification=snapshot.classification, notice=notice(snapshot),
                              total=len(courses), offset=offset, limit=limit, courses=courses[offset:offset + limit])


def section_options(snapshot: CatalogSnapshot, course_id: str, term_id: str) -> SectionOptions:
    term = next((item for item in snapshot.terms if item.id == term_id), None)
    if not term or not any(c.id == course_id and c.edition == term.catalog_edition for c in snapshot.courses):
        raise LookupError('Unknown course or term in this dataset.')
    return SectionOptions(snapshot_id=snapshot.id, classification=snapshot.classification, notice=notice(snapshot),
        course_id=course_id, term_id=term_id,
        sections=[s for s in snapshot.sections if s.term_id == term_id and s.course_id == course_id],
        bundles=[b for b in snapshot.bundles if b.term_id == term_id and b.course_id == course_id], sources=snapshot.sources)
