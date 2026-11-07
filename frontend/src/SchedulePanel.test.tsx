// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { SchedulePanel } from './SchedulePanel';
import { jsonResponse, reviewedFixture, sectionsFixture, suggestionsFixture, termsFixture } from './planning.test-fixtures';
import type { components } from './api/schema';
import type { SelectedCourse } from './CoursePlanner';

const selected: SelectedCourse[] = [{ course_id:'DEMO 101', edition:'2026-2027', title:'Fictional History', required:true,
  source:'suggestion', matches:suggestionsFixture.suggestions[0].matches }];
const props = { reviewed:reviewedFixture, term:termsFixture[0], selected,
  ruleRevisions:suggestionsFixture.resolution.rule_revisions, snapshotDigest:suggestionsFixture.snapshot_digest };
const result: components['schemas']['ScheduleResult'] = {
  audit_revision:reviewedFixture.revision, snapshot_id:'fictional-demo-v1', snapshot_digest:'a'.repeat(64),
  term_id:'sample-spring-2027', timezone:'America/New_York', classification:'fictional',notice:termsFixture[0].notice,
  sources:termsFixture[0].sources,rule_revisions:props.ruleRevisions, search_complete:true,nodes_visited:3,feasible_schedules_found:1,
  filtered_courses:[{course_id:'DEMO 101',available_bundles:1,rejected_reasons:{time_window:1}}],diagnostics:[],warnings:['Eligibility is unverified.'],
  schedules:[{id:'schedule-1',total_credits:3,score:900,score_breakdown:{credit_distance:900},reasons:['3 credits; target 12'],
    courses:[{course_id:'DEMO 101',title:'Fictional History',bundle_id:'bundle-101-a',credits:3,sections:sectionsFixture.sections,
      source:'suggestion',possible_requirement_ids:['req-1'],possible_requirement_labels:['Engagement with the Human Past']}]}],
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('generation stays disabled during suggestion refresh and until suggested-course data is ready', async () => {
  const fetch=vi.fn().mockImplementation(() => jsonResponse(result)); vi.stubGlobal('fetch',fetch);
  const {rerender}=render(<SchedulePanel {...props} suggestionsLoading />);
  const user=userEvent.setup();
  const updating=screen.getByRole('button',{name:'Updating course suggestions…'}) as HTMLButtonElement;
  expect(updating.disabled).toBe(true);
  await user.click(updating);
  expect(fetch).not.toHaveBeenCalled();
  rerender(<SchedulePanel {...props} ruleRevisions={undefined} snapshotDigest={undefined} />);
  expect((screen.getByRole('button',{name:'Generate schedules'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('status').textContent).toContain('Retry suggestions above');
  rerender(<SchedulePanel {...props} />);
  const ready=screen.getByRole('button',{name:'Generate schedules'}) as HTMLButtonElement;
  expect(ready.disabled).toBe(false);
  await user.click(ready);
  expect(await screen.findByRole('article',{name:'Schedule option 1'})).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(1);
});

test('preferences and required-course restrictions are sent with pinned provenance', async () => {
  const fetch=vi.fn().mockImplementation(() => jsonResponse(result)); vi.stubGlobal('fetch',fetch);
  render(<SchedulePanel {...props} />);
  const user=userEvent.setup();
  await user.clear(screen.getByLabelText('Target credits')); await user.type(screen.getByLabelText('Target credits'),'3');
  await user.click(screen.getByLabelText('Avoid Friday'));
  await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  expect(await screen.findByRole('article',{name:'Schedule option 1'})).toBeTruthy();
  const body=JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.preferences.target_credits).toBe(3);
  expect(body.preferences.avoided_days).toEqual([4]);
  expect(body.selections[0]).toEqual({course_id:'DEMO 101',required:true,source:'suggestion',requirement_ids:['req-1']});
  expect(body.expected_snapshot_digest).toBe(props.snapshotDigest);
  expect(screen.getByText('Monday 09:00–09:50')).toBeTruthy();
});

test('invalid credit ordering is explained before sending a request', async () => {
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
  render(<SchedulePanel {...props} />);
  const user=userEvent.setup();
  await user.clear(screen.getByLabelText('Minimum credits')); await user.type(screen.getByLabelText('Minimum credits'),'15');
  await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  expect((await screen.findByRole('alert')).textContent).toContain('minimum, target and maximum');
  expect(fetch).not.toHaveBeenCalled();
});

test('no-results diagnostics and partial search remain distinct from proven impossibility', async () => {
  vi.stubGlobal('fetch',vi.fn().mockImplementation(() => jsonResponse({...result,schedules:[],search_complete:false,
    diagnostics:[{code:'search_limit',message:'Search stopped before all possibilities were checked.',course_ids:[],suggestions:['Try fewer course alternatives.']}]})));
  render(<SchedulePanel {...props} />);
  const user=userEvent.setup(); await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  expect(await screen.findByText('No schedule found')).toBeTruthy();
  expect(screen.getByText(/Partial search:/)).toBeTruthy();
  expect(screen.getByText('Try fewer course alternatives.')).toBeTruthy();
});

test('editing preferences invalidates results and ignores a late response', async () => {
  let resolve!: (value:Response)=>void;
  vi.stubGlobal('fetch',vi.fn().mockImplementation(() => new Promise<Response>(done=>{resolve=done;})));
  render(<SchedulePanel {...props} />);
  const user=userEvent.setup();await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  await user.click(screen.getByLabelText('Avoid Monday'));
  resolve(await jsonResponse(result));
  await user.selectOptions(screen.getByLabelText('Preferred time of day'),'afternoon');
  expect(screen.queryByRole('article',{name:'Schedule option 1'})).toBeNull();
  expect((screen.getByRole('button',{name:'Generate schedules'}) as HTMLButtonElement).disabled).toBe(false);
});

test('changing selected courses clears completed results and requests can be retried after errors', async () => {
  const fetch=vi.fn().mockRejectedValueOnce(new Error('Scheduling server unavailable.')).mockImplementation(()=>jsonResponse(result));
  vi.stubGlobal('fetch',fetch);
  const {rerender}=render(<SchedulePanel {...props} />);
  const user=userEvent.setup();await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  expect((await screen.findByRole('alert')).textContent).toContain('unavailable');
  await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  expect(await screen.findByRole('article',{name:'Schedule option 1'})).toBeTruthy();
  rerender(<SchedulePanel {...props} selected={[]} />);
  expect(screen.queryByRole('article',{name:'Schedule option 1'})).toBeNull();
  expect((screen.getByRole('button',{name:'Generate schedules'}) as HTMLButtonElement).disabled).toBe(true);
});

test('preferred selection pins export to that option and clears with preferences', async () => {
  let finish!: (value:Response)=>void;
  const fetch=vi.fn().mockImplementationOnce(() => jsonResponse({...result,schedules:[result.schedules[0],{...result.schedules[0],id:'schedule-2'}]}))
    .mockImplementation(() => new Promise<Response>(resolve=>{finish=resolve;}));
  vi.stubGlobal('fetch',fetch);
  const create=vi.fn();vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:vi.fn()}));
  render(<SchedulePanel {...props} />);
  const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Generate schedules'}));
  expect((await screen.findByRole('button',{name:'Download schedule JSON'}) as HTMLButtonElement).disabled).toBe(true);
  await user.selectOptions(screen.getByLabelText('View option'),'1');
  await user.click(screen.getByRole('button',{name:'Use option 2 as preferred'}));
  await user.selectOptions(screen.getByLabelText('View option'),'0');
  await user.click(screen.getByRole('button',{name:'Download schedule JSON'}));
  const payload=JSON.parse(fetch.mock.calls[1][1].body);
  expect(payload.schedule_id).toBe('schedule-2');
  expect(payload.schedule_request.expected_snapshot_digest).toBe(result.snapshot_digest);
  expect(payload.schedule_request.rule_revisions).toEqual(result.rule_revisions);
  expect(screen.getByRole('heading',{name:/Keep preferred option 2/})).toBeTruthy();
  await user.click(screen.getByLabelText('Avoid Friday'));
  finish(new Response('{}',{headers:{'Content-Type':'application/json'}}));
  await Promise.resolve();
  expect(create).not.toHaveBeenCalled();
  expect(document.querySelector('.print-sheet')).toBeNull();
  expect(fetch.mock.calls[1][1].signal.aborted).toBe(true);
});
