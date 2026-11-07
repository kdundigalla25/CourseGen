// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { AuditReview } from './AuditReview';
import type { components } from './api/schema';

type Draft = components['schemas']['AuditDraft'];

function draft(): Draft {
  return {
    schema_version: '1', parser_version: 'tracker-0.2', support: 'tracker_structure_detected', review_state: 'needs_review', page_count: 1,
    pages: [{ number: 1, text: 'Synthetic source text' }],
    curriculum: { starting_year: 2024, entry_term: '2024 Fall', reported_catalog_year: '2024-2025', method: 'unresolved', program_terms: { 'Computer Science Major': '2025 Fall' }, evidence: [] },
    attempts: [{ id: 'attempt-1', course_id: 'COMP 210', raw_course_code: 'COMP 210', title: 'SYNTHETIC COURSE', term: '2025 Fall', credits: 3, grade: null, status: 'unknown', origin: 'institution', needs_review: true, evidence: [{ page: 1, line: 10, text: 'COMP 210 SYNTHETIC COURSE 3.00 2025 Fall' }] }],
    requirements: [{ id: 'req-group', label: 'Major requirements', kind: 'group', reported_status: 'not_satisfied', completion: 'unknown', needs_review: false }, { id: 'req-1', parent_id: 'req-group', label: 'Required course', kind: 'course', reported_status: 'unknown', completion: 'unknown', attempt_ids: ['attempt-1'], amounts: [{ unit: 'courses', required: 1, taken: 0, needed: 1 }], needs_review: true }],
    issues: [{ id: 'flag-1', code: 'unknown_attempt_status', message: 'Confirm the course status.', target_id: 'attempt-1', review_required: true }],
  };
}

const acknowledgment = /I've checked my details against my Tracker/;
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('starting year and program terms are independently editable and source is immutable', async () => {
  const original = draft();
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ review_state: 'confirmed', revision: 'revision-1', audit: original, changes: [], unresolved_issues: [] }) });
  vi.stubGlobal('fetch', fetch);
  render(<AuditReview original={original} />);
  const user = userEvent.setup();
  const confirm = screen.getByRole('button', { name: 'Use this progress' }) as HTMLButtonElement;
  expect(confirm.disabled).toBe(true);
  await user.clear(screen.getByLabelText('Requirement term for Computer Science Major'));
  await user.type(screen.getByLabelText('Requirement term for Computer Science Major'), '2026 Fall');
  expect((screen.getByLabelText('Starting term') as HTMLInputElement).value).toBe('2024 Fall');
  await user.click(screen.getByLabelText(acknowledgment));
  await user.click(confirm);
  expect(await screen.findByText('Your review is complete.')).toBeTruthy();
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.original.curriculum.program_terms['Computer Science Major']).toBe('2025 Fall');
  expect(body.edited.curriculum.program_terms['Computer Science Major']).toBe('2026 Fall');
  expect(body.acknowledged_issue_ids).toEqual(['flag-1']);
  expect(original.curriculum?.program_terms?.['Computer Science Major']).toBe('2025 Fall');
  await user.type(screen.getByLabelText('Reported catalog year'), ' ');
  expect(screen.queryByText('Your review is complete.')).toBeNull();
  expect(confirm.disabled).toBe(true);
});

test('course correction and deletion also update requirement links', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: { message: 'Check your edits.' } }) });
  vi.stubGlobal('fetch', fetch);
  render(<AuditReview original={draft()} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Check COMP 210' }));
  const card = screen.getByRole('article', { name: 'Course record COMP 210' });
  expect(document.activeElement).toBe(card);
  await user.selectOptions(within(card).getByLabelText('Course status'), 'in_progress');
  expect(screen.queryByRole('button', { name: 'Check COMP 210' })).toBeNull();
  await user.click(within(card).getByRole('button', { name: 'Remove course attempt-1' }));
  await user.click(screen.getByRole('button', { name: 'Requirements' }));
  expect(screen.getAllByText('Course evidence links (0)').length).toBe(2);
  await user.click(screen.getByLabelText(acknowledgment));
  await user.click(screen.getByRole('button', { name: 'Use this progress' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Check your edits.');
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.edited.attempts).toEqual([]);
  expect(body.edited.requirements.find((row: { id: string }) => row.id === 'req-1').attempt_ids).toEqual([]);
});

test('a student can add a course and correct an unmet requirement count', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: { message: 'Saved request inspected.' } }) });
  vi.stubGlobal('fetch', fetch);
  render(<AuditReview original={draft()} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Course history' }));
  await user.click(screen.getByRole('button', { name: '+ Add course record' }));
  const card = screen.getByRole('article', { name: 'Course record new' });
  await user.type(within(card).getByLabelText('Course code'), 'MATH 231');
  await user.type(within(card).getByLabelText('Course title'), 'CALCULUS');
  await user.type(within(card).getByLabelText('Term'), '2024 Fall');
  await user.type(within(card).getByLabelText('Credits'), '4');
  await user.selectOptions(within(card).getByLabelText('Course status'), 'completed');
  await user.click(screen.getByRole('button', { name: 'Requirements' }));
  const requirement = screen.getByRole('article', { name: 'Requirement Required course' });
  await user.selectOptions(within(requirement).getByLabelText('Reported status'), 'not_satisfied');
  await user.clear(within(requirement).getByLabelText('needed'));
  await user.type(within(requirement).getByLabelText('needed'), '2');
  await user.click(screen.getByLabelText(acknowledgment));
  await user.click(screen.getByRole('button', { name: 'Use this progress' }));
  await screen.findByRole('alert');
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.edited.attempts[1].course_id).toBe('MATH 231');
  expect(body.edited.attempts[1].status).toBe('completed');
  expect(body.edited.requirements[1].amounts[0].needed).toBe(2);
});

test('failed review requests preserve edits and allow retry', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Review service unavailable.')));
  render(<AuditReview original={draft()} />);
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText('Starting term'));
  await user.type(screen.getByLabelText('Starting term'), '2024 Spr');
  await user.click(screen.getByLabelText(acknowledgment));
  await user.click(screen.getByRole('button', { name: 'Use this progress' }));
  expect((await screen.findByRole('alert')).textContent).toContain('unavailable');
  expect((screen.getByLabelText('Starting term') as HTMLInputElement).value).toBe('2024 Spr');
  expect((screen.getByRole('button', { name: 'Use this progress' }) as HTMLButtonElement).disabled).toBe(false);
});
