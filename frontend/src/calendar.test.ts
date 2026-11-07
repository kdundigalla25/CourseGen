import { expect, test } from 'vitest';
import { events, firstWeek, monday, shiftDate } from './calendar';
import { sectionsFixture, termsFixture } from './planning.test-fixtures';
import type { components } from './api/schema';
const schedule: components['schemas']['CandidateSchedule'] = { id:'test',total_credits:3,score:0,score_breakdown:{},reasons:[],courses:[{
  course_id:'DEMO 101',title:'History',bundle_id:'test',credits:3,sections:sectionsFixture.sections,source:'manual',possible_requirement_ids:[],possible_requirement_labels:[],
}] };
test('date-only arithmetic stays on Monday through daylight saving and year boundaries', () => {
  expect(monday('2027-03-14')).toBe('2027-03-08');
  expect(monday('2027-01-01')).toBe('2026-12-28');
  expect(shiftDate('2027-03-14',1)).toBe('2027-03-15');
});
test('phased meetings use actual weekday dates while missing dates remain explicit', () => {
  const term = {...termsFixture[0].term,start_date:'2027-01-11',end_date:'2027-05-07'};
  const phased = structuredClone(schedule);
  phased.courses[0].sections[0].meetings = [{kind:'timed',weekday:0,start_minute:540,end_minute:590,start_date:'2027-03-01',end_date:'2027-03-15'}];
  expect(firstWeek([phased],term)).toBe('2027-01-11');
  expect(events(phased,term,'2027-02-22')).toHaveLength(0);
  expect(events(phased,term,'2027-03-15')[0].date).toBe('2027-03-15');
  expect(events(phased,term,'2027-03-22')).toHaveLength(0);
  const undated = {...term,start_date:null,end_date:null};
  expect(events(schedule,undated,'')[0].uncertain).toBe(true);
  expect(firstWeek([schedule],undated)).toBe('');
});
