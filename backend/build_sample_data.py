"""Reproduce the deliberately fictional development dataset. Never fetches UNC data."""
import json
from pathlib import Path

from app.catalog_models import CatalogSnapshot

source = 'fictional-authoring-v1'
edition = '2026-2027'
term = 'sample-spring-2027'
courses, sections, bundles, designations = [], [], [], []
titles = ['Worlds and Stories', 'Creative Studio', 'Investigation and Evidence', 'Investigation Lab', 'Public Questions', 'Quantitative Practice', 'Language Workshop', 'Research Studio', 'Independent Project', 'Inquiry Seminar']
attributes = ['FC-PAST', 'FC-CREATE', 'FC-NATSCI', 'FC-LAB', 'FC-VALUES', 'FC-QUANT', 'FC-GLOBAL', 'RESEARCH', 'FC-KNOWING', 'FY-SEMINAR']
for number, (title, attribute) in enumerate(zip(titles, attributes), 101):
    code = f'DEMO {number}'
    credits = 4 if number == 103 else 1 if number == 104 else 2 if number == 109 else 3
    courses.append(dict(id=code, title='Fictional: ' + title, credits_min=1 if number == 109 else credits,
        credits_max=3 if number == 109 else credits, edition=edition, source_snapshot_id=source,
        description='Invented solely for testing; not a UNC catalog course.'))
    designations.append(dict(course_id=code, edition=edition, attribute_id=attribute, source_snapshot_id=source))
    for index, suffix in enumerate(('A', 'B')):
        identity = f'demo-{number}-{suffix.lower()}'
        start = 540 + (number - 101) % 4 * 60 + index * 180
        weekday = (number - 101) % 5
        meetings = [dict(kind='timed', weekday=weekday, start_minute=start, end_minute=start+50)]
        modality = 'in_person'
        if number == 107 and index == 1:
            meetings = [dict(kind='timed', weekday=2, start_minute=1080, end_minute=1150)]
        if number == 108 and index == 1:
            meetings = [dict(kind='asynchronous')]
            modality = 'asynchronous'
        if number == 110 and index == 1:
            meetings = [dict(kind='unknown')]
            modality = 'unknown'
        if number == 102 and index == 0:
            meetings = [dict(kind='timed', weekday=0, start_minute=550, end_minute=600)] # Conflicts with DEMO 101 A.
        if number == 105 and index == 0:
            meetings[0].update(start_date='2027-01-11', end_date='2027-03-05')
        ids = [identity]
        linked = [identity + '-lab'] if number == 103 else []
        sections.append(dict(id=identity, term_id=term, course_id=code, number=suffix, source_snapshot_id=source,
            component='lab' if number == 104 else 'seminar' if number == 110 else 'lecture', meetings=meetings,
            modality=modality, credit_value=credits, required_component_ids=linked,
            linkage_status='verified' if linked else 'not_required', instructor='Fictional Instructor'))
        if linked:
            ids.extend(linked)
            sections.append(dict(id=linked[0], term_id=term, course_id=code, number=suffix+'L', source_snapshot_id=source,
                component='lab', meetings=[dict(kind='timed', weekday=3, start_minute=840+index*90, end_minute=920+index*90)],
                modality='in_person', credit_value=0, linkage_status='verified', required_component_ids=[identity]))
        bundles.append(dict(id=f'bundle-{number}-{suffix.lower()}', term_id=term, course_id=code, section_ids=ids,
            credits=credits, source_snapshot_id=source))
# A historical edition proves attributes are not timeless. No historical offering is implied.
courses.append(dict(id='DEMO 101', title='Fictional: Earlier Worlds and Stories', credits_min=3, credits_max=3,
                    edition='2024-2025', source_snapshot_id=source))
designations.append(dict(course_id='DEMO 101', edition='2024-2025', attribute_id='FC-AESTH', source_snapshot_id=source))
# One section-specific designation must not be projected onto every section.
designations.append(dict(course_id='DEMO 102', edition=edition, attribute_id='RESEARCH', term_id=term,
                         section_id='demo-102-b', source_snapshot_id=source))
snapshot = CatalogSnapshot.model_validate(dict(id='fictional-demo-v1', classification='fictional',
    description='Fictional sample data, not official UNC offerings. All courses, sections and dates are invented.',
    created_at='2026-11-07T12:00:00-05:00', sources=[dict(id=source, classification='fictional', edition='development-v1', adapter_version='hand-authored-1')],
    courses=courses, designations=designations,
    terms=[dict(id=term, name='Fictional Spring 2027', catalog_edition=edition, start_date='2027-01-11', end_date='2027-05-07')],
    sections=sections, bundles=bundles))
target = Path(__file__).resolve().parents[1] / 'data' / 'samples' / 'fictional-demo-v1.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(snapshot.model_dump_json(indent=2) + '\n', encoding='utf-8')
print(f'Created {len(courses)} course editions / 10 fictional courses, {len(sections)} sections and {len(bundles)} bundles')
