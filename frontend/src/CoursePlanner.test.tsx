// @vitest-environment jsdom
import { cleanup, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { CoursePlanner } from './CoursePlanner';
import { App } from './App';
import { catalogFixture, draftFixture, jsonResponse, reviewedFixture, sectionsFixture, suggestionsFixture, termsFixture } from './planning.test-fixtures';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mockFetch() {
  return vi.fn((url: string, _options?: RequestInit) => {
    if (url === '/api/v1/terms') return jsonResponse(termsFixture);
    if (url === '/api/v1/recommendations') return jsonResponse(suggestionsFixture);
    if (url.includes('/sections?')) return jsonResponse(sectionsFixture);
    if (url.startsWith('/api/v1/courses?')) return jsonResponse(catalogFixture);
    if (url === '/api/v1/audits/parse') return jsonResponse(draftFixture);
    if (url === '/api/v1/audits/review') return jsonResponse(reviewedFixture);
    throw new Error(`Unexpected test request: ${url}`);
  });
}

async function selectTerm() {
  const user = userEvent.setup();
  await waitFor(() => expect((screen.getByLabelText('Semester and course data') as HTMLSelectElement).disabled).toBe(false));
  await user.selectOptions(screen.getByLabelText('Semester and course data'), JSON.stringify(['fictional-demo-v1', 'sample-spring-2027']));
  await screen.findByRole('article', { name: 'Suggestion DEMO 101' });
  return user;
}

test('suggestions explain provenance and can be selected, required or removed without duplicates', async () => {
  const fetch = mockFetch(); vi.stubGlobal('fetch', fetch);
  render(<CoursePlanner reviewed={reviewedFixture} />);
  const user = await selectTerm();
  expect(screen.getByText('Fictional sample data. Not official UNC offerings.')).toBeTruthy();
  expect(screen.getByText('Could help with:')).toBeTruthy();
  const card = screen.getByRole('article', { name: 'Suggestion DEMO 101' });
  await user.click(within(card).getByRole('button', { name: 'Add DEMO 101' }));
  const selection = screen.getByRole('region', { name: 'Courses to consider' });
  const required = within(selection).getByLabelText('Must include DEMO 101') as HTMLInputElement;
  expect(required.checked).toBe(false);
  await user.click(required);
  expect(required.checked).toBe(true);
  expect((within(card).getByRole('button', { name: 'Added DEMO 101' }) as HTMLButtonElement).disabled).toBe(true);
  await user.click(within(selection).getByRole('button', { name: 'Remove DEMO 101' }));
  expect(within(selection).queryByLabelText('Must include DEMO 101')).toBeNull();
  const payload = JSON.parse(fetch.mock.calls.find(call => call[0] === '/api/v1/recommendations')![1]!.body as string);
  expect(payload.reviewed.revision).toBe(reviewedFixture.revision);
});

test('manual search selection checks section availability and does not invent requirement coverage', async () => {
  const fetch = mockFetch(); vi.stubGlobal('fetch', fetch);
  render(<CoursePlanner reviewed={reviewedFixture} />);
  const user = await selectTerm();
  await user.type(screen.getByLabelText('Course code or title'), 'History');
  await user.click(screen.getByRole('button', { name: 'Search courses' }));
  await waitFor(() => expect(fetch.mock.calls.some(call => call[0].includes('q=History'))).toBe(true));
  await user.click(await screen.findByRole('button', { name: 'Add from search DEMO 101' }));
  expect(await screen.findByText('Added from search; requirement coverage is unverified.')).toBeTruthy();
  expect(fetch.mock.calls.some(call => call[0].includes('DEMO%20101/sections?'))).toBe(true);
});

test('manual search cannot select a course whose only bundle has unknown meetings', async () => {
  const fetch = mockFetch(); const fallback = fetch.getMockImplementation()!;
  fetch.mockImplementation((url, options) => url.includes('/sections?') ? jsonResponse({ ...sectionsFixture, sections: sectionsFixture.sections.map(section => ({ ...section, meetings: [{ kind: 'unknown' }] })) }) : fallback(url, options));
  vi.stubGlobal('fetch', fetch);
  render(<CoursePlanner reviewed={reviewedFixture} />);
  const user = await selectTerm();
  await user.click(screen.getByRole('button', { name: 'Add from search DEMO 101' }));
  expect((await screen.findByRole('alert')).textContent).toContain('no verified section combination');
  expect(screen.queryByLabelText('Must include DEMO 101')).toBeNull();
});

test('failed suggestions can be retried and do not conceal the search path', async () => {
  const fetch = mockFetch(); const fallback = fetch.getMockImplementation()!;
  let first = true;
  fetch.mockImplementation((url, options) => {
    if (url === '/api/v1/recommendations' && first) { first = false; return jsonResponse({ error: { message: 'Suggestions unavailable.' } }, false); }
    return fallback(url, options);
  });
  vi.stubGlobal('fetch', fetch);
  render(<CoursePlanner reviewed={reviewedFixture} />);
  const user = userEvent.setup();
  await waitFor(() => expect((screen.getByLabelText('Semester and course data') as HTMLSelectElement).disabled).toBe(false));
  await user.selectOptions(screen.getByLabelText('Semester and course data'), JSON.stringify(['fictional-demo-v1', 'sample-spring-2027']));
  expect((await screen.findByRole('alert')).textContent).toContain('Suggestions unavailable');
  expect(screen.getByRole('region', { name: 'Course search' })).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Retry suggestions' }));
  expect(await screen.findByRole('article', { name: 'Suggestion DEMO 101' })).toBeTruthy();
});

test('editing reviewed progress removes suggestions and the selected course list', async () => {
  vi.stubGlobal('fetch', mockFetch());
  render(<App />);
  const user = userEvent.setup();
  await user.upload(screen.getByLabelText(/Choose your Tar Heel Tracker/), new File(['%PDF-test'], 'synthetic.pdf', { type: 'application/pdf' }));
  await user.click(screen.getByRole('button', { name: /Extract Tracker text/ }));
  expect(screen.queryByLabelText('Semester and course data')).toBeNull();
  await user.click(await screen.findByLabelText(/I've checked my details against my Tracker/));
  await user.click(screen.getByRole('button', { name: 'Use this progress' }));
  await selectTerm();
  await user.click(screen.getByRole('button', { name: 'Add DEMO 101' }));
  expect(screen.getByLabelText('Must include DEMO 101')).toBeTruthy();
  await user.clear(screen.getByLabelText('Starting term'));
  expect(screen.queryByLabelText('Semester and course data')).toBeNull();
  expect(screen.queryByLabelText('Must include DEMO 101')).toBeNull();
});

test('changing term discards choices and ignores late results from the previous request', async () => {
  let resolveOld!: (value: Response) => void;
  const fetch = mockFetch(); const fallback = fetch.getMockImplementation()!;
  const second = { ...termsFixture[0], term: { ...termsFixture[0].term, id: 'second', name: 'Another fictional term' } };
  fetch.mockImplementation((url, options) => {
    if (url === '/api/v1/terms') return jsonResponse([...termsFixture, second]);
    if (url === '/api/v1/recommendations') {
      const request = JSON.parse(options!.body as string);
      if (request.term_id === 'sample-spring-2027') return new Promise<Response>(resolve => { resolveOld = resolve; });
      return jsonResponse({ ...suggestionsFixture, term_id: 'second', suggestions: [] });
    }
    return fallback(url, options);
  });
  vi.stubGlobal('fetch', fetch);
  render(<CoursePlanner reviewed={reviewedFixture} />);
  const user = userEvent.setup();
  await waitFor(() => expect((screen.getByLabelText('Semester and course data') as HTMLSelectElement).disabled).toBe(false));
  await user.selectOptions(screen.getByLabelText('Semester and course data'), JSON.stringify(['fictional-demo-v1', 'sample-spring-2027']));
  await waitFor(() => expect(resolveOld).toBeTruthy());
  await user.selectOptions(screen.getByLabelText('Semester and course data'), JSON.stringify(['fictional-demo-v1', 'second']));
  await screen.findByText(/No new selectable course matches/);
  resolveOld(await jsonResponse(suggestionsFixture));
  await waitFor(() => expect(screen.queryByRole('article', { name: 'Suggestion DEMO 101' })).toBeNull());
});
