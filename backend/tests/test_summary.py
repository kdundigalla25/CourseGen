from test_parser import parse


def test_degree_summary_preserves_completed_remaining_and_in_progress_separately():
    draft = parse('Program Requirement', 'Degree Requirement Stats',
                  'Minimum Cumulative Grade', 'Point 2.000 .000',
                  'Minimum Degree Hours 120 40 80 14', 'Minimum 45 Hours at UNC 45 0 45 14',
                  'Not Satisfied: Degree Requirements')
    policies = [r for r in draft.requirements if r.kind == 'policy']
    assert len(policies) == 3
    gpa, hours, residency = policies
    assert gpa.amounts[0].required == 2 and gpa.amounts[0].taken == 0
    assert hours.amounts[0].taken == 40 and hours.amounts[0].needed == 80 and hours.amounts[0].in_progress == 14
    assert residency.amounts[0].required == 45
    assert all(r.reported_status == 'unknown' and r.needs_review for r in policies)


def test_unsupported_requirement_prose_remains_visible_and_flagged():
    draft = parse('Program Requirement', 'Not Satisfied: An unfamiliar policy',
                  'Requires special approval by the department', 'and an additional condition.',
                  'Extra explanatory condition beyond the heading.', 'Satisfied: Other requirement')
    assert any(i.code == 'unparsed_requirement_text' for i in draft.issues)
    assert any('Extra explanatory' in e.text for e in draft.requirements[0].evidence)
