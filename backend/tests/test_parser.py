import json
from pathlib import Path

import pytest

from app.audit_parser import parse_pages
from app.models import ExtractedPage


def fixture_draft(name):
    fixture = json.loads((Path(__file__).parent / 'fixtures' / f'{name}.json').read_text(encoding='utf-8'))
    pages = [ExtractedPage(number=n, text='\n'.join(lines)) for n, lines in enumerate(fixture['pages'], 1)]
    return parse_pages(pages), fixture['expected']


def parse(*lines):
    return parse_pages([ExtractedPage(number=1, text='\n'.join(lines))])


@pytest.mark.parametrize('name', ['cohort_2024', 'cohort_2026'])
def test_representative_synthetic_expectations(name):
    draft, expected = fixture_draft(name)
    assert len(draft.attempts) == expected['attempts']
    assert len(draft.requirements) == expected['requirements']
    assert sum(a.status == 'in_progress' for a in draft.attempts) == expected['in_progress']
    assert sum(a.status == 'completed' for a in draft.attempts) == expected['completed']
    assert draft.curriculum.gen_ed_version is None
    assert all(r.label and r.evidence for r in draft.requirements)


def test_independent_program_terms_and_wrapped_course_across_pages():
    draft, _ = fixture_draft('cohort_2024')
    assert draft.curriculum.starting_year == 2024
    assert draft.curriculum.program_terms['Computer Science (BS) Major'] == '2025 Fall'
    course = next(a for a in draft.attempts if a.course_id == 'PLAN 101')
    assert course.title == 'SYNTHETIC URBAN STUDIES'
    assert {e.page for e in course.evidence} == {1, 2}
    assert course.grade == 'A-'
    assert course.status == 'completed'


def test_references_do_not_duplicate_attempts_or_override_in_progress():
    draft, _ = fixture_draft('cohort_2024')
    course = next(a for a in draft.attempts if a.course_id == 'COMP 426')
    assert sum(a.course_id == 'COMP 426' for a in draft.attempts) == 1
    requirement = next(r for r in draft.requirements if r.label == 'Additional COMP Courses')
    assert requirement.reported_status == 'satisfied'
    assert requirement.completion == 'mixed'
    assert course.id in requirement.attempt_ids
    assert any(i.code == 'satisfied_with_in_progress' and i.target_id == requirement.id for i in draft.issues)


def test_counts_policies_non_course_and_nested_requirements_are_preserved():
    draft, _ = fixture_draft('cohort_2026')
    policy = next(r for r in draft.requirements if r.label.startswith('Admission'))
    assert policy.kind == 'policy' and policy.reported_status == 'unknown'
    assert policy.label.endswith('General College')
    elective = next(r for r in draft.requirements if r.label == 'Business Electives' and r.amounts)
    assert elective.amounts[0].unit == 'credits'
    assert elective.amounts[0].needed == 19.5
    campus = next(r for r in draft.requirements if r.label == 'Campus Life Experience' and r.amounts)
    assert campus.kind == 'non_course' and campus.amounts[0].needed == 7
    assert campus.attempt_ids == []
    assert any('Synthetic campus event' in e.text for e in campus.evidence)
    course_req = next(r for r in draft.requirements if r.label == 'BUSI 401')
    parent = next(r for r in draft.requirements if r.id == course_req.parent_id)
    assert parent.label == 'Business Administration Major Courses'
    assert next(r for r in draft.requirements if r.id == parent.parent_id).label == 'Major: Business Administration'


def test_tallies_do_not_invent_satisfied_requirements_or_drop_duplicate_awards():
    draft, _ = fixture_draft('cohort_2026')
    ways = [r for r in draft.requirements if r.label == 'Ways of Knowing']
    assert len(ways) == 1 and ways[0].reported_status == 'not_satisfied'
    awards = [a for a in draft.attempts if a.raw_course_code == 'AMST ----']
    assert len(awards) == 2 and all(a.course_id is None and a.origin == 'transfer' for a in awards)
    placement = next(a for a in draft.attempts if a.course_id == 'SPAN 101')
    assert placement.origin == 'exam' and placement.credits == 0


def test_repeated_terms_missing_grade_and_failing_grade_remain_distinct():
    draft = parse('Program Requirement', 'Satisfied: Electives',
                  'COMP  110 EXAMPLE 3.00 2024 Fall F', 'COMP  110 EXAMPLE 3.00 2025 Spr A',
                  'COMP  210 WRAPPED TITLE', 'STRUCTURES', '3.00 2025 Fall',
                  'Not Satisfied: Ways of Knowing')
    assert len(draft.attempts) == 3
    assert [str(a.status) for a in draft.attempts] == ['unknown', 'completed', 'unknown']
    assert any(i.code == 'unknown_attempt_status' for i in draft.issues)
    assert draft.attempts[2].title == 'WRAPPED TITLE STRUCTURES'


def test_truncated_row_does_not_consume_next_requirement():
    draft = parse('Program Requirement', 'Satisfied: Electives', 'COMP  210 INCOMPLETE', 'Not Satisfied: Ways of Knowing')
    assert draft.attempts[0].term is None
    assert draft.requirements[-1].label == 'Ways of Knowing'
    assert any(i.code == 'incomplete_course_row' for i in draft.issues)


def test_missing_or_conflicting_metadata_is_not_guessed_from_major_or_catalog():
    draft = parse('Program Requirement', ' Computer Science Major 2025 Fall', 'Catalog Year 2024-2025', 'Satisfied: Foundations')
    assert draft.curriculum.starting_year is None
    assert draft.curriculum.entry_term is None
    assert draft.curriculum.program_terms['Computer Science Major'] == '2025 Fall'
    conflict = parse('Program Requirement', ' Undergraduate Career 2024 Fall', ' Undergraduate Career 2026 Fall',
                     'Catalog Year 2024-2025', 'Catalog Year 2026-2027', 'Satisfied: Foundations')
    assert conflict.curriculum.starting_year is None and conflict.curriculum.reported_catalog_year is None
    assert {'conflicting_entry_terms', 'conflicting_catalog_years'} <= {i.code for i in conflict.issues}


def test_conflicting_grade_references_are_preserved_for_review():
    draft = parse('Program Requirement', 'Satisfied: Electives',
                  'COMP  210 EXAMPLE 3.00 2025 Fall A',
                  'Not Satisfied: Other requirement', 'COMP  210 EXAMPLE 3.00 2025 Fall F')
    assert len(draft.attempts) == 2
    assert all(a.status == 'unknown' for a in draft.attempts)
    assert any(i.code == 'conflicting_attempt_records' for i in draft.issues)


def test_large_document_flags_structural_truncation_instead_of_silent_success():
    draft = parse('Program Requirement', *[f'Not Satisfied: Requirement {index}' for index in range(505)])
    assert len(draft.requirements) == 500
    assert any(issue.code == 'parser_item_limit' and issue.review_required for issue in draft.issues)
