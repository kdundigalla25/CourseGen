"""Explain potential matches without recomputing or certifying degree completion."""
import re
import hashlib

from app.catalog import notice
from app.catalog_models import CatalogSnapshot
from app.curriculum import normalized, resolve_reviewed
from app.models import AuditRequirement, Course, ReviewedAudit
from app.recommendation_models import CourseSuggestion, ExcludedCourse, ManualRequirement, RecommendationResult, RequirementMatch
from app.rule_models import AvailableCurricula, RequirementDefinition, RulePack

COUNTING_NOTICE = 'Each match is a possibility, not combined degree credit. A course may not count toward all listed requirements; counting restrictions still need verification.'


def program_base(value: str) -> str:
    return normalized(re.sub(r'\b(?:major|minor|program|concentration)\b', '', value, flags=re.I))


def recommend(reviewed: ReviewedAudit, snapshot: CatalogSnapshot, term_id: str, packs: AvailableCurricula) -> RecommendationResult:
    resolution = resolve_reviewed(reviewed, packs)
    term = next((term for term in snapshot.terms if term.id == term_id), None)
    if not term:
        raise LookupError('Unknown term in this dataset.')
    audit = reviewed.audit
    requirements = {item.id: item for item in audit.requirements}
    parents = {item.parent_id for item in audit.requirements if item.parent_id}
    selected_ids = {item.pack_id for item in resolution.programs if item.pack_id}
    gen_ed = next((pack for pack in packs.gen_ed if pack.id == resolution.gen_ed_version), None)
    programs = [pack for pack in packs.programs if pack.id in selected_ids]
    catalog = {course.id: course for course in snapshot.courses if course.edition == term.catalog_edition}
    sections = {section.id: section for section in snapshot.sections if section.term_id == term.id}
    suggestions: dict[str, CourseSuggestion] = {}
    manual: list[ManualRequirement] = []
    excluded: list[ExcludedCourse] = []

    def manual_item(item: AuditRequirement, reason, message):
        manual.append(ManualRequirement(requirement_id=item.id, label=item.label, reason=reason,
                                       message=message, amounts=item.amounts, evidence=item.evidence))

    def matching_rules(item):
        ancestors = []
        parent = item.parent_id
        while parent:
            ancestors.append(requirements[parent].label)
            parent = requirements[parent].parent_id
        contexts = [value.split(':', 1)[1].strip() for value in [item.label, *ancestors]
                    if re.match(r'^(?:Major|Minor|Additional|Prerequisites):', value, re.I)]
        candidates: list[RulePack] = []
        if not contexts and gen_ed:
            candidates.append(gen_ed)
        for pack in programs:
            aliases = [program_base(name) for name in pack.audit_program_names]
            if not contexts or any(alias and alias in program_base(context) for alias in aliases for context in contexts):
                candidates.append(pack)
        return [(pack, rule) for pack in candidates for rule in pack.requirements
                if normalized(item.label) in {normalized(alias) for alias in rule.audit_labels}]

    def qualifies(bundle, rule: RequirementDefinition, course_id: str):
        if rule.minimum_credits is not None and bundle.credits < rule.minimum_credits:
            return False
        if rule.kind != 'attribute':
            return True
        return any(d.course_id == course_id and d.edition == term.catalog_edition and d.attribute_id in rule.attribute_ids
                   and (d.term_id is None or (d.term_id == term.id and d.section_id in bundle.section_ids)) for d in snapshot.designations)

    for item in audit.requirements:
        # Structural headings are not additional course requirements.
        if item.id in parents:
            continue
        if normalized(item.label) in {'in progress courses', 'major courses in progress'}:
            continue
        if item.reported_status == 'satisfied':
            continue
        if item.reported_status == 'unknown':
            manual_item(item, 'status_unknown', 'Check the requirement status in your Tracker before choosing courses for it.')
            continue
        if item.kind == 'non_course':
            manual_item(item, 'non_course', 'This is an activity or milestone, not a course to add to your schedule.')
            continue
        context_ids = {item.id}
        ancestor = item.parent_id
        while ancestor:
            context_ids.add(ancestor)
            ancestor = requirements[ancestor].parent_id
        if any(issue.code == 'unparsed_requirement_text' and issue.target_id in context_ids for issue in reviewed.unresolved_issues):
            manual_item(item, 'policy_or_elective', 'This requirement or its group contains a condition that could not be interpreted. Check the source before choosing courses for it.')
            continue
        matches = matching_rules(item)
        if not matches:
            manual_item(item, 'curriculum_unresolved' if resolution.state != 'selected' else 'unmapped',
                        'No verified course mapping is available for this item. Check your curriculum/program details or choose a course manually.')
            continue
        if len(matches) != 1:
            manual_item(item, 'ambiguous_mapping', 'More than one supported rule matches this description. Confirm the requirement and its program group.')
            continue
        pack, rule = matches[0]
        direct = rule.kind in {'course', 'any_of'} and bool(rule.course_ids) and not rule.child_ids
        attribute = rule.kind == 'attribute' and bool(rule.attribute_ids)
        if item.kind in {'policy', 'non_course'} or rule.support != 'candidate_matching' or not (direct or attribute):
            manual_item(item, 'policy_or_elective', 'This elective pool, policy or course combination needs manual interpretation; no automatic fulfillment is assumed.')
            continue
        course_ids = set(rule.course_ids) if direct else {d.course_id for d in snapshot.designations
            if d.edition == term.catalog_edition and d.attribute_id in rule.attribute_ids and (d.term_id is None or d.term_id == term.id)}
        selectable = False
        for course_id in sorted(course_ids):
            course: Course | None = catalog.get(course_id)
            attempts = [attempt for attempt in audit.attempts if attempt.course_id == course_id]
            reason = 'in_progress' if any(a.status == 'in_progress' for a in attempts) else 'completed' if any(a.status == 'completed' for a in attempts) and not (course and course.repeatable) else None
            if reason:
                excluded.append(ExcludedCourse(requirement_id=item.id, course_id=course_id, reason=reason,
                    message='Already recorded as in progress; it was not suggested again.' if reason == 'in_progress' else 'Already recorded as completed/credited. Verify grades and repeat eligibility before adding it again.'))
                continue
            offered = [section for section in sections.values() if section.course_id == course_id]
            bundles = [bundle for bundle in snapshot.bundles if bundle.term_id == term.id and bundle.course_id == course_id and qualifies(bundle, rule, course_id)]
            known = [bundle for bundle in bundles if all(meeting.kind not in {'unknown', 'arranged'} for key in bundle.section_ids for meeting in sections[key].meetings)]
            availability = 'missing_catalog' if course is None else 'not_offered' if not offered else 'available' if known else 'unknown_meetings' if bundles else 'no_qualifying_sections'
            notes = list(rule.notes)
            if rule.minimum_grade:
                notes.append(f'The published rule requires a grade of {rule.minimum_grade} or better; this is not an eligibility check.')
            notes.extend(policy.description for policy in pack.policies if rule.id in policy.requirement_ids)
            explanation = f'{course_id} is an explicit course option in the applicable published rule.' if direct else f'The {term.catalog_edition} dataset records a qualifying {", ".join(rule.attribute_ids)} designation. Only the listed section combinations have been matched.'
            match = RequirementMatch(requirement_id=item.id, label=item.label, pack_id=pack.id, rule_id=rule.id,
                match_type='direct_course' if direct else 'attribute', explanation=explanation,
                qualifying_bundle_ids=[bundle.id for bundle in known],
                section_options=[' + '.join(sections[key].number for key in bundle.section_ids) for bundle in known],
                audit_evidence=item.evidence, sources=[source for source in pack.sources if source.id in rule.source_ids], notes=notes)
            if course_id not in suggestions:
                warnings = ['Prerequisites, corequisites, grades and enrollment restrictions have not been verified. Check the official catalog before enrolling.']
                if any(a.status == 'unknown' for a in attempts):
                    warnings.append('Your history includes an uncertain attempt for this course. Check it before selecting the course again.')
                if course and course.repeatable and any(a.status == 'completed' for a in attempts):
                    warnings.append('The dataset marks this course repeatable. Verify repeat-credit limits and requirement applicability.')
                conditional = False
                if course and course.prerequisite_text:
                    for attempt in audit.attempts:
                        if attempt.course_id and attempt.status == 'in_progress' and re.search(rf'(?<!\w){re.escape(attempt.course_id)}(?!\w)', course.prerequisite_text, re.I):
                            conditional = True
                            warnings.append(f'Prerequisite text mentions {attempt.course_id}, which is in progress. Completion and eligibility must be verified.')
                suggestions[course_id] = CourseSuggestion(course_id=course_id, edition=term.catalog_edition,
                    title=course.title if course else None, credits_min=course.credits_min if course else None,
                    credits_max=course.credits_max if course else None, availability=availability,
                    selectable=bool(known), prerequisite_text=course.prerequisite_text if course else None,
                    eligibility='conditional' if conditional else 'unverified', warnings=warnings, matches=[])
            suggestion = suggestions[course_id]
            suggestion.matches.append(match)
            if known:
                suggestion.selectable = True
                suggestion.availability = 'available'
                selectable = True
        if not selectable:
            manual_item(item, 'no_available_candidate', 'No new course with a qualifying, known-time section combination could be selected for this requirement in this dataset. Catalog options and excluded attempts remain visible.')

    ranked = sorted(suggestions.values(), key=lambda s: (not s.selectable, not any(m.match_type == 'direct_course' for m in s.matches), s.course_id))
    return RecommendationResult(audit_revision=reviewed.revision, snapshot_id=snapshot.id,
        snapshot_digest=hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest(), term_id=term.id,
        classification=snapshot.classification, notice=notice(snapshot), sources=snapshot.sources,
        resolution=resolution, suggestions=ranked, manual_requirements=manual, excluded_courses=excluded,
        counting_notice=COUNTING_NOTICE, warnings=resolution.warnings)
