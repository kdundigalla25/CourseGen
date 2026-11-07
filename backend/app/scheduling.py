"""Bounded deterministic backtracking. Hard constraints are never relaxed."""
import hashlib
from collections import Counter
from decimal import Decimal
from itertools import combinations

from app.audit_review import InvalidReview
from app.catalog import notice
from app.catalog_models import CatalogSnapshot, SectionBundle, Term
from app.models import Meeting
from app.recommendations import COUNTING_NOTICE, recommend
from app.rule_models import AvailableCurricula
from app.scheduling_models import (
    CandidateSchedule, FilteredCourse, ScheduleDiagnostic, ScheduledCourse,
    SchedulePreferences, ScheduleRequest, ScheduleResult,
)

WEIGHTS = {'credit_distance': 100, 'time_preference': 1 / 30, 'gap_minutes': 1 / 15, 'meeting_days': 20}


def dates_overlap(a: Meeting, b: Meeting, term: Term) -> bool:
    starts = [value for value in (a.start_date or term.start_date, b.start_date or term.start_date) if value]
    ends = [value for value in (a.end_date or term.end_date, b.end_date or term.end_date) if value]
    start, end = max(starts) if starts else None, min(ends) if ends else None
    if start and end:
        if start > end:
            return False
        # A shared date range matters only if the applicable weekday occurs in it.
        if a.weekday is not None:
            return (end - start).days >= (a.weekday - start.weekday()) % 7
    return True


def meetings_conflict(a: Meeting, b: Meeting, term: Term) -> bool:
    return (a.kind == b.kind == 'timed' and a.weekday == b.weekday
            and a.start_minute < b.end_minute and b.start_minute < a.end_minute
            and dates_overlap(a, b, term))


def score_schedule(meetings: list[Meeting], credits: Decimal, preferences: SchedulePreferences, term: Term):
    timed = [meeting for meeting in meetings if meeting.kind == 'timed']
    days = {meeting.weekday for meeting in timed}
    nonpreferred = sum(max(0, meeting.end_minute - max(meeting.start_minute, 720)) if preferences.preferred_time == 'morning'
                       else max(0, min(meeting.end_minute, 720) - meeting.start_minute) if preferences.preferred_time == 'afternoon'
                       else 0 for meeting in timed)
    gaps = 0
    for day in days:
        ordered = sorted((m for m in timed if m.weekday == day), key=lambda m: (m.start_minute, m.end_minute))
        for a, b in zip(ordered, ordered[1:]):
            if dates_overlap(a, b, term):
                gaps += max(0, b.start_minute - a.end_minute)
    breakdown = {
        'credit_distance': float(abs(credits - Decimal(str(preferences.target_credits)))) * WEIGHTS['credit_distance'],
        'time_preference': nonpreferred * WEIGHTS['time_preference'],
        'gaps': gaps * WEIGHTS['gap_minutes'],
        'meeting_days': len(days) * WEIGHTS['meeting_days'] if preferences.compact_days else 0,
    }
    reasons = [f'{credits:g} credits; target {preferences.target_credits:g}', f'{len(days)} days with fixed meetings',
               f'{gaps} gap minutes in the weekly meeting template']
    if preferences.preferred_time != 'none':
        reasons.append(f'{nonpreferred} fixed-meeting minutes outside your preferred {preferences.preferred_time} period')
    return round(sum(breakdown.values()), 6), {key: round(value, 6) for key, value in breakdown.items()}, reasons


def generate_schedules(request: ScheduleRequest, snapshot: CatalogSnapshot, packs: AvailableCurricula) -> ScheduleResult:
    recommendation = recommend(request.reviewed, snapshot, request.term_id, packs)
    if request.expected_snapshot_digest is not None and request.expected_snapshot_digest != recommendation.snapshot_digest:
        raise InvalidReview('Course data changed. Refresh the selected semester data before generating schedules.', code='stale_dataset')
    revisions = recommendation.resolution.rule_revisions
    if request.rule_revisions is not None and request.rule_revisions != revisions:
        raise InvalidReview('Curriculum definitions changed. Refresh your suggestions before generating schedules.', code='stale_rules')
    if len({selection.course_id for selection in request.selections}) != len(request.selections):
        raise InvalidReview('Select each course only once.')
    term = next(t for t in snapshot.terms if t.id == request.term_id)
    courses = {c.id: c for c in snapshot.courses if c.edition == term.catalog_edition}
    sections = {s.id: s for s in snapshot.sections if s.term_id == term.id}
    suggested = {s.course_id: s for s in recommendation.suggestions}
    diagnostics, filtered = [], []
    options: dict[str, list[SectionBundle]] = {}
    selection_map = {selection.course_id: selection for selection in request.selections}
    bundle_meetings, bundle_groups = {}, {}

    for selection in request.selections:
        if selection.course_id not in courses:
            raise InvalidReview('A selected course is not in the selected term catalog.', [selection.course_id])
        allowed = None
        if selection.source == 'suggestion':
            candidate = suggested.get(selection.course_id)
            if not candidate or not selection.requirement_ids or request.rule_revisions is None or request.expected_snapshot_digest is None:
                raise InvalidReview('Refresh the course suggestions and select a current suggested course.', code='stale_suggestion')
            matched = {match.requirement_id: match for match in candidate.matches}
            if not set(selection.requirement_ids) <= matched.keys():
                raise InvalidReview('A selected requirement match is no longer available.', code='stale_suggestion')
            allowed = {key for identity in selection.requirement_ids for key in matched[identity].qualifying_bundle_ids}
        elif selection.requirement_ids:
            raise InvalidReview('Manual course selections cannot assert verified requirement matches.')
        rejected = Counter()
        available = []
        for bundle in sorted(snapshot.bundles, key=lambda b: b.id):
            if bundle.term_id != term.id or bundle.course_id != selection.course_id:
                continue
            meetings = [meeting for key in bundle.section_ids for meeting in sections[key].meetings]
            bundle_meetings[bundle.id] = meetings
            bundle_groups[bundle.id] = {sections[key].crosslist_group_id for key in bundle.section_ids if sections[key].crosslist_group_id}
            reason = None
            if allowed is not None and bundle.id not in allowed:
                reason = 'requirement_section_restriction'
            elif any(m.kind in {'unknown', 'arranged'} for m in meetings):
                reason = 'unknown_meeting_time'
            elif any(m.kind == 'timed' and m.weekday in request.preferences.avoided_days for m in meetings):
                reason = 'avoided_day'
            elif any(m.kind == 'timed' and (m.start_minute < request.preferences.earliest_start or m.end_minute > request.preferences.latest_end) for m in meetings):
                reason = 'time_window'
            elif any(meetings_conflict(a, b, term) for a, b in combinations(meetings, 2)):
                reason = 'internal_component_conflict'
            elif len([key for key in bundle.section_ids if sections[key].crosslist_group_id]) != len(bundle_groups[bundle.id]):
                reason = 'internal_crosslist_duplicate'
            if reason:
                rejected[reason] += 1
            else:
                available.append(bundle)
        options[selection.course_id] = available
        filtered.append(FilteredCourse(course_id=selection.course_id, available_bundles=len(available), rejected_reasons=dict(rejected)))
        if selection.required and not available:
            diagnostics.append(ScheduleDiagnostic(code='required_course_unavailable', course_ids=[selection.course_id],
                message=f'{selection.course_id} has no section combination that meets the current restrictions.',
                suggestions=['Check the rejected-section reasons, choose another dataset, or change the relevant day/time/course restriction.']))

    def incompatible(a, b):
        return bool(bundle_groups[a.id] & bundle_groups[b.id]) or any(meetings_conflict(x, y, term) for x in bundle_meetings[a.id] for y in bundle_meetings[b.id])

    ordered = sorted(request.selections, key=lambda s: (not s.required, len(options[s.course_id]), s.course_id))
    minimum, maximum = Decimal(str(request.preferences.minimum_credits)), Decimal(str(request.preferences.maximum_credits))
    lower = sum((min(Decimal(str(b.credits)) for b in options[s.course_id]) for s in ordered if s.required and options[s.course_id]), Decimal(0))
    upper = sum((max((Decimal(str(b.credits)) for b in options[s.course_id]), default=Decimal(0)) for s in ordered), Decimal(0))
    if lower > maximum:
        diagnostics.append(ScheduleDiagnostic(code='required_credits_exceed_maximum', message='Required courses exceed your maximum credits.', suggestions=['Raise the maximum or make a course optional.']))
    if upper < minimum:
        diagnostics.append(ScheduleDiagnostic(code='minimum_credits_unreachable', message='The available courses cannot reach your minimum credits.', suggestions=['Lower the minimum or add more available courses.']))
    pair_checks = 0
    for a, b in combinations((s for s in ordered if s.required and options[s.course_id]), 2):
        proven = True
        for x in options[a.course_id]:
            for y in options[b.course_id]:
                if pair_checks >= 10000:
                    proven = False
                    break
                pair_checks += 1
                if not incompatible(x, y):
                    proven = False
                    break
            if not proven:
                break
        if proven:
            diagnostics.append(ScheduleDiagnostic(code='required_courses_conflict', course_ids=[a.course_id, b.course_id],
                message=f'Every available combination of {a.course_id} and {b.course_id} conflicts or duplicates a cross-listed class.',
                suggestions=['Change course choices or relax a restriction that filtered alternate sections.']))

    suffix_max = [Decimal(0)] * (len(ordered) + 1)
    suffix_min = [Decimal(0)] * (len(ordered) + 1)
    for i in range(len(ordered) - 1, -1, -1):
        choices = options[ordered[i].course_id]
        suffix_max[i] = suffix_max[i + 1] + max((Decimal(str(b.credits)) for b in choices), default=Decimal(0))
        suffix_min[i] = suffix_min[i + 1] + (min((Decimal(str(b.credits)) for b in choices), default=Decimal(0)) if ordered[i].required else Decimal(0))
    retained = []
    nodes, found, truncated = 0, 0, False

    def explore(index, chosen, credits):
        nonlocal nodes, found, truncated
        if nodes >= request.node_budget:
            truncated = True
            return
        nodes += 1
        if credits + suffix_min[index] > maximum or credits + suffix_max[index] < minimum:
            return
        if index == len(ordered):
            if not chosen or not minimum <= credits <= maximum:
                return
            found += 1
            signature = tuple(sorted(key for bundle in chosen for key in bundle.section_ids))
            meetings = [m for bundle in chosen for m in bundle_meetings[bundle.id]]
            score, breakdown, reasons = score_schedule(meetings, credits, request.preferences, term)
            rank = (score, signature)
            if len(retained) == request.result_limit and rank >= retained[-1][0]:
                return
            planned = []
            for bundle in sorted(chosen, key=lambda b: b.course_id):
                selection = selection_map[bundle.course_id]
                matches = [match for match in suggested[bundle.course_id].matches if match.requirement_id in selection.requirement_ids and bundle.id in match.qualifying_bundle_ids] if selection.source == 'suggestion' else []
                planned.append(ScheduledCourse(course_id=bundle.course_id, title=courses[bundle.course_id].title,
                    bundle_id=bundle.id, credits=bundle.credits, sections=[sections[key] for key in bundle.section_ids], source=selection.source,
                    possible_requirement_ids=[m.requirement_id for m in matches], possible_requirement_labels=[m.label for m in matches]))
            candidate = CandidateSchedule(id=hashlib.sha256('\0'.join([snapshot.id, term.id, *signature]).encode()).hexdigest()[:16], courses=planned,
                total_credits=float(credits), score=score, score_breakdown=breakdown, reasons=reasons)
            if not any(key[1] == signature for key, _ in retained):
                retained.append((rank, candidate))
                retained.sort(key=lambda item: item[0])
                del retained[request.result_limit:]
            return
        selection = ordered[index]
        for bundle in options[selection.course_id]:
            value = credits + Decimal(str(bundle.credits))
            if value <= maximum and not any(incompatible(bundle, other) for other in chosen):
                explore(index + 1, [*chosen, bundle], value)
            if truncated:
                return
        if not selection.required:
            explore(index + 1, chosen, credits)

    if not diagnostics:
        explore(0, [], Decimal(0))
    if truncated:
        diagnostics.append(ScheduleDiagnostic(code='search_limit', message='The search limit was reached. Results are partial; absence of a schedule does not prove that none exists.', suggestions=['Consider fewer course alternatives or try a larger bounded search.']))
    elif not retained and not diagnostics:
        diagnostics.append(ScheduleDiagnostic(code='no_feasible_schedule', message='No combination meets all of the selected course, credit and meeting constraints.', suggestions=['Try fewer required courses, a wider time window, different days or a different credit range.']))
    warnings = [COUNTING_NOTICE, 'Eligibility and seat availability are unverified. No hard constraint was relaxed.',
                'Unknown or arranged meeting times are excluded; genuinely asynchronous sections have no fixed-time conflicts.',
                'Missing meeting dates use the term dates when known; otherwise shared weekdays are conservatively treated as potentially concurrent.',
                'Credit values come from explicit bundles. Variable-credit alternatives require explicit validated bundles; no credit amount was invented.']
    if any(not selection.required and not options[selection.course_id] for selection in ordered):
        warnings.append('Some optional courses have no usable sections and will be omitted.')
    return ScheduleResult(audit_revision=request.reviewed.revision, snapshot_id=snapshot.id,
        snapshot_digest=hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest(), term_id=term.id, timezone=term.timezone,
        classification=snapshot.classification, notice=notice(snapshot), sources=snapshot.sources, rule_revisions=revisions,
        schedules=[candidate for _, candidate in retained], search_complete=not truncated, nodes_visited=nodes,
        feasible_schedules_found=found, filtered_courses=filtered, diagnostics=diagnostics, warnings=warnings)
