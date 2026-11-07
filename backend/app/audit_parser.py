"""Conservative parser for the two observed text-based Tar Heel Tracker layouts.

No requirement fulfillment rules or current-year assumptions live here. The audit's
reported statuses and counts are evidence, not a recomputed degree evaluation.
"""
import re
from collections import Counter

from app.models import (
    AttemptStatus, AuditDraft, AuditRequirement, CourseAttempt, Evidence,
    ExtractedPage, Issue, RequirementAmount,
)

TERM = r"\d{4}\s+(?:Fall|Spr(?:ing)?|SumII|SumI|Summer(?:\s+[I12]+)?)"
COURSE = re.compile(r"^([A-Z]{2,5})\s+(\d{1,3}[A-Za-z]*|----)\s+(.+)")
TAIL = re.compile(rf"(?P<credits>\d+\.\d{{2}})\s+(?P<term>{TERM})(?:\s+(?P<grade>[A-Z][A-Z+\-]*))?\s*$")
STATUS = re.compile(r"^(?:Overall Requirement\s+)?(Not Satisfied|Satisfied):\s*(.+)$", re.I)
PASSING = {"A", "A+", "A-", "B", "B+", "B-", "C", "C+", "C-", "D", "D+", "D-", "PS", "P", "S", "TR", "BE", "PL"}
MARKERS = "∆△Δ?··•"


def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def content(text: str) -> str:
    return text.strip().lstrip(MARKERS).strip()


def kind_for(label: str, leaf: bool) -> str:
    lower = label.lower()
    if "campus life" in lower:
        return "non_course"
    if any(word in lower for word in ("gpa", "admission", "limit of", "course check")):
        return "policy"
    if "elective" in lower or "total hours" in lower:
        return "elective"
    if not leaf:
        return "group"
    if re.search(r"\b[A-Z]{2,5}\s+\d{1,3}[A-Za-z]*\b", label):
        return "course"
    return "unknown"


def update_completion(draft: AuditDraft) -> None:
    """Compute evidence state; never turn an audit status into a course grade."""
    attempts = {attempt.id: attempt for attempt in draft.attempts}
    children: dict[str, list[AuditRequirement]] = {}
    for requirement in draft.requirements:
        if requirement.parent_id:
            children.setdefault(requirement.parent_id, []).append(requirement)

    def visit(requirement: AuditRequirement) -> set[str]:
        ids = set(requirement.attempt_ids)
        for child in children.get(requirement.id, []):
            ids |= visit(child)
        states = {str(attempts[key].status) for key in ids if key in attempts}
        if not states or "unknown" in states:
            requirement.completion = "unknown"
        elif len(states) > 1:
            requirement.completion = "mixed"
        else:
            requirement.completion = next(iter(states))
        return ids

    for requirement in draft.requirements:
        if requirement.parent_id is None:
            visit(requirement)


def parse_pages(pages: list[ExtractedPage]) -> AuditDraft:
    text = "\n".join(page.text for page in pages)
    detected = "Program Requirement" in text and bool(re.search(r"(?:Not Satisfied|Satisfied):", text))
    draft = AuditDraft(
        support="tracker_structure_detected" if detected else "unsupported",
        review_state="needs_review" if detected else "extraction_only",
        page_count=len(pages), pages=pages, issues=[],
    )

    def issue(code: str, message: str, target: str | None = None, page: int | None = None, required: bool = True):
        draft.issues.append(Issue(id=f"issue-{len(draft.issues) + 1}", code=code, message=message,
                                  target_id=target, page=page, review_required=required))

    if not detected:
        issue("unsupported_layout", "This layout is unsupported. Text remains available, but no degree progress was inferred.")
        for page in pages:
            if not page.text.strip():
                issue("page_without_text", "This page has no readable text; extraction may be incomplete.", page=page.number)
        return draft

    rows = [(Evidence(page=page.number, line=n, text=line), line)
            for page in pages for n, line in enumerate(page.text.splitlines(), 1) if line.strip()]
    # Summary-table policies have no explicit satisfaction marker. Preserve the
    # numeric columns and ask for review rather than interpreting them as grades.
    number = r"(?:\d+(?:\.\d+)?|\.\d+)"
    for index, (evidence, raw) in enumerate(rows):
        line = tidy(raw)
        fragments = [evidence]
        if line == "Minimum Cumulative Grade" and index + 1 < len(rows):
            line += " " + tidy(rows[index + 1][1])
            fragments.append(rows[index + 1][0])
        hours = re.fullmatch(rf"(Minimum (?:Degree Hours|45 Hours at UNC))\s+({number})\s+({number})\s+({number})\s+({number})", line)
        gpa = re.fullmatch(rf"(Minimum Cumulative Grade Point)\s+({number})\s+({number})", line)
        if hours or gpa:
            matched = hours or gpa
            requirement = AuditRequirement(id=f"requirement-{len(draft.requirements) + 1}", label=matched[1], kind="policy",
                reported_status="unknown", needs_review=True, evidence=fragments,
                amounts=[RequirementAmount(unit="credits" if hours else "gpa", required=float(matched[2]), taken=float(matched[3]),
                    needed=float(matched[4]) if hours else None, in_progress=float(matched[5]) if hours else None)])
            draft.requirements.append(requirement)
            issue("unknown_requirement_status", "The summary reports numeric degree-policy values without an explicit status. Verify them; no satisfaction was inferred.", requirement.id, evidence.page)
    curriculum = draft.curriculum
    catalogs: set[str] = set()
    entries: set[str] = set()
    program_terms: dict[str, set[str]] = {}
    for evidence, raw in rows:
        line = tidy(raw)
        catalog = re.search(r"Catalog Year\s+(\d{4})[-–](\d{4})", line)
        if catalog:
            catalogs.add(f"{catalog[1]}-{catalog[2]}")
            curriculum.evidence.append(evidence)
        entry = re.fullmatch(rf"Undergraduate Career\s+({TERM})", line)
        if entry:
            entries.add(entry[1])
            curriculum.evidence.append(evidence)
        program = re.fullmatch(rf"(.+\b(?:Program|Major|Minor|Concentration))\s+({TERM})", line)
        if program and not line.startswith("Undergraduate"):
            program_terms.setdefault(program[1], set()).add(program[2])
            curriculum.evidence.append(evidence)
    if len(catalogs) == 1:
        curriculum.reported_catalog_year = next(iter(catalogs))
    elif len(catalogs) > 1:
        issue("conflicting_catalog_years", "Several catalog-year labels were found. Confirm the applicable label in metadata review.")
    if len(entries) == 1:
        curriculum.entry_term = next(iter(entries))
        curriculum.starting_year = int(curriculum.entry_term[:4])
    elif len(entries) > 1:
        issue("conflicting_entry_terms", "Several undergraduate career terms were found. Confirm your starting term.")
    else:
        issue("missing_entry_term", "Starting term was not identified. Enter it if known; a catalog label alone does not prove a starting year.")
    for name, terms in program_terms.items():
        if len(terms) == 1:
            curriculum.program_terms[name] = next(iter(terms))
        else:
            issue("conflicting_program_terms", f"Several requirement terms were found for {name}. Confirm its term.")
    if curriculum.starting_year and curriculum.reported_catalog_year and not curriculum.reported_catalog_year.startswith(str(curriculum.starting_year)):
        issue("entry_catalog_disagreement", "The career starting year and catalog-year label differ. Confirm applicability; neither overrides the other automatically.")
    issue("curriculum_unresolved", "Gen Ed rule-pack selection is not implemented yet. Starting-term metadata and the listed requirements are preserved for that step.", required=False)
    issue("pdf_summary", "The Tracker PDF is a summary and may omit requirements. Check the full official Tracker when reviewing.", required=False)

    stack: dict[int, AuditRequirement] = {}
    current: AuditRequirement | None = None
    tally = False
    in_progress_block = False
    by_key: dict[tuple, CourseAttempt] = {}
    occurrences: Counter = Counter()
    pending_progress: set[str] = set()
    i = 0
    while i < len(rows):
        if len(draft.attempts) >= 500 or len(draft.requirements) >= 500:
            issue("parser_item_limit", "This document exceeds the supported structured-record count. Review the source for omitted items; the draft is incomplete.")
            break
        evidence, raw = rows[i]
        line = content(raw)
        if line in {"Focus Capacities Tally", "Electives", "Electives and Non-Degree Applicable"} and not raw.strip().startswith(tuple(MARKERS)):
            tally = line == "Focus Capacities Tally"
            current = None
            stack.clear()
            in_progress_block = False
            occurrences.clear()
            i += 1
            continue

        course = COURSE.match(line)
        if course:
            fragments = [evidence]
            joined = line
            # Do not consume the next requirement or course when a row is truncated.
            while not TAIL.search(joined) and i + 1 < len(rows) and len(fragments) < 7:
                next_evidence, next_raw = rows[i + 1]
                next_line = content(next_raw)
                if STATUS.match(next_line) or COURSE.match(next_line) or next_raw.strip().startswith(tuple(MARKERS)):
                    break
                if next_line in {"Focus Capacities Tally", "Electives", "Electives and Non-Degree Applicable"}:
                    break
                if re.match(rf".+\b(?:Career|Program|Major|Minor)\s+{TERM}$", next_line):
                    break
                joined += " " + next_line
                fragments.append(next_evidence)
                i += 1
            tail = TAIL.search(joined)
            raw_code = f"{course[1]} {course[2].upper()}"
            title = tidy(joined[course.start(3):tail.start()] if tail else joined[course.start(3):])
            term = tail['term'] if tail else None
            grade = tail['grade'] if tail else None
            credits = float(tail['credits']) if tail else None
            key = (raw_code, title, term, grade, credits)
            occurrence_key = (current.id if current else f"unassigned-{tally}", key)
            occurrences[occurrence_key] += 1
            ordinal = 1 if tally else occurrences[occurrence_key]
            # Tally references corroborate the first occurrence; they are not new attempts.
            identity = (*key, ordinal)
            attempt = by_key.get(identity)
            if attempt is None:
                attempt = CourseAttempt(id=f"attempt-{len(draft.attempts) + 1}",
                    course_id=raw_code if course[2] != "----" else None,
                    raw_course_code=raw_code, title=title, term=term, grade=grade, credits=credits,
                    status="completed" if grade in PASSING else "unknown",
                    origin="transfer" if grade == "TR" else "exam" if grade in {"BE", "PL"} else "institution" if term else "unknown")
                by_key[identity] = attempt
                draft.attempts.append(attempt)
                if course[2] == "----":
                    attempt.needs_review = True
                    issue("non_catalog_credit", "This is a general/transfer credit record without a selectable course code. Repeated identical records may represent distinct awards; verify them.", attempt.id, evidence.page)
                if ordinal > 1:
                    attempt.needs_review = True
                    issue("duplicate_attempt", "Repeated rows in one block may represent separate attempts or awards. Both were retained; verify them.", attempt.id, evidence.page)
                if not tail:
                    attempt.needs_review = True
                    issue("incomplete_course_row", "Course row lacks a recognized credit/term ending. Complete or remove it in review.", attempt.id, evidence.page)
            attempt.evidence.extend(fragments)
            if current and not tally:
                if attempt.id not in current.attempt_ids:
                    current.attempt_ids.append(attempt.id)
            if in_progress_block and not grade:
                pending_progress.add(attempt.id)
            i += 1
            continue

        status_match = STATUS.match(line)
        raw_prefix = raw.strip()
        marked_leaf = raw_prefix.startswith(("∆", "△", "Δ", "??"))
        if not tally and (status_match or marked_leaf):
            label = status_match[2] if status_match else line
            # Wrapped headings continue until a structured marker, course or count line.
            fragments = [evidence]
            while i + 1 < len(rows):
                next_evidence, next_raw = rows[i + 1]
                following = content(next_raw)
                if STATUS.match(following) or COURSE.match(following) or next_raw.strip().startswith(tuple(MARKERS)):
                    break
                if following in {"Focus Capacities Tally", "Electives", "Electives and Non-Degree Applicable"}:
                    break
                if following.startswith(("Required Major Courses", "Assured Enrollment")):
                    break
                if TAIL.search(following) or re.search(r"\d{4}-\d{2}-\d{2}", following):
                    break
                label += " " + following
                fragments.append(next_evidence)
                i += 1
                # Observed continuations are short; don't absorb arbitrary paragraphs.
                if len(fragments) >= 3:
                    break
            depth = 2 if marked_leaf else 1 if len(raw) - len(raw.lstrip()) >= 2 else 0
            parent = (stack.get(1) or stack.get(0)) if depth == 2 else stack.get(0) if depth == 1 else None
            requirement = AuditRequirement(id=f"requirement-{len(draft.requirements) + 1}", parent_id=parent.id if parent else None,
                label=tidy(label), reported_status="not_satisfied" if status_match and status_match[1].lower() == "not satisfied" else "satisfied" if status_match else "unknown",
                kind=kind_for(label, marked_leaf), evidence=fragments)
            draft.requirements.append(requirement)
            for level in list(stack):
                if level >= depth:
                    del stack[level]
            stack[depth] = requirement
            current = requirement
            occurrences.clear()
            in_progress_block = "in-progress courses" in requirement.label.lower() and "major courses" not in requirement.label.lower()
            if not status_match:
                requirement.needs_review = True
                issue("unknown_requirement_status", "No explicit satisfied/not-satisfied status was found. Confirm this item's status.", requirement.id, evidence.page)
            if marked_leaf and requirement.kind in {"unknown", "policy", "elective", "non_course"}:
                issue("unmapped_requirement", "This requirement is preserved for review; no automatic course-fulfillment rule has been assigned.", requirement.id, evidence.page, required=False)
            i += 1
            continue

        amount = re.match(r"(Courses|Units|GPA):\s*(.+)", line, re.I)
        if current and not tally and amount:
            values = {name: float(value) for value, name in re.findall(r"(\d+(?:\.\d+)?)\s+(required|taken|needed|actual)", amount[2], re.I)}
            current.amounts.append(RequirementAmount(unit={"courses": "courses", "units": "credits", "gpa": "gpa"}[amount[1].lower()],
                required=values.get("required"), taken=values.get("taken", values.get("actual")), needed=values.get("needed")))
            current.evidence.append(evidence)
        elif current and current.kind == "non_course" and not tally:
            # Events/date rows are evidence for a milestone, never invented courses.
            current.evidence.append(evidence)
        elif current and not tally and not line.startswith(("Required Major Courses", "Assured Enrollment")):
            current.evidence.append(evidence)
            current.needs_review = True
            if not any(item.code == "unparsed_requirement_text" and item.target_id == current.id for item in draft.issues):
                issue("unparsed_requirement_text", "Additional text in this requirement could not be interpreted. Check its source evidence for missing conditions.", current.id, evidence.page)
        i += 1

    variants: dict[tuple, list[CourseAttempt]] = {}
    for attempt in draft.attempts:
        if attempt.course_id and attempt.term:
            variants.setdefault((attempt.course_id, attempt.title, attempt.term, attempt.credits), []).append(attempt)
    conflicts: set[str] = set()
    for records in variants.values():
        if len({attempt.grade for attempt in records}) > 1:
            for attempt in records:
                conflicts.add(attempt.id)
                issue("conflicting_attempt_records", "References to this course/term disagree on the grade or credit marker. Both records were retained; verify which represent distinct attempts.", attempt.id)
    for attempt in draft.attempts:
        if attempt.id in pending_progress:
            attempt.status = AttemptStatus.in_progress
        if attempt.id in conflicts:
            attempt.status = AttemptStatus.unknown
        if attempt.status == "unknown":
            attempt.needs_review = True
            issue("unknown_attempt_status", "This attempt has no recognized passing/credit marker or explicit in-progress context. Confirm its status.", attempt.id)
    update_completion(draft)
    for requirement in draft.requirements:
        if requirement.reported_status == "satisfied" and requirement.completion in {"in_progress", "mixed"}:
            issue("satisfied_with_in_progress", "The Tracker reports this requirement satisfied using in-progress work. It is not evidence of final completion.", requirement.id, required=False)
    for page in pages:
        if not page.text.strip():
            issue("page_without_text", "This page has no readable text; review the PDF for missing items.", page=page.number)
    return draft
