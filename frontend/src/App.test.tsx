// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from './App';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function submit() {
  const user = userEvent.setup();
  await user.upload(screen.getByLabelText(/Choose your Tar Heel Tracker/), new File(['%PDF-test'], 'tracker.pdf', { type: 'application/pdf' }));
  await user.click(screen.getByRole('button', { name: /Extract Tracker text/ }));
  return user;
}

test('successful extraction exposes text and can clear the session', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    page_count: 1, support: 'tracker_structure_detected',
    curriculum: { reported_catalog_year: '2026-2027' },
    issues: [{ code: 'extraction_only', message: 'Text extraction only.' }],
    pages: [{ number: 1, text: 'Not Satisfied: Ways of Knowing' }],
  }) });
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  const user = await submit();
  expect(await screen.findByText('2026-2027')).toBeTruthy();
  expect(screen.getByText('Not Satisfied: Ways of Knowing')).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Clear session' }));
  expect(screen.queryByText('2026-2027')).toBeNull();
  expect((screen.getByRole('button', { name: /Extract Tracker text/ }) as HTMLButtonElement).disabled).toBe(true);
});

test('safe backend errors are displayed and upload becomes available again', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: { message: 'Scanned PDFs are not supported yet.' } }) }));
  render(<App />);
  await submit();
  expect((await screen.findByRole('alert')).textContent).toContain('Scanned PDFs are not supported');
  expect((screen.getByRole('button', { name: /Extract Tracker text/ }) as HTMLButtonElement).disabled).toBe(false);
});

test('network errors do not leave the interface in a loading state', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Could not reach the local server.')));
  render(<App />);
  await submit();
  expect((await screen.findByRole('alert')).textContent).toContain('Could not reach');
  expect(screen.queryByText('Reading your PDF. This can take a few seconds.')).toBeNull();
});

test('oversized files are rejected without uploading student data', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  render(<App />);
  const file = new File(['%PDF-test'], 'large.pdf', { type: 'application/pdf' });
  Object.defineProperty(file, 'size', { value: 10 * 1024 * 1024 + 1 });
  const user = userEvent.setup();
  await user.upload(screen.getByLabelText(/Choose your Tar Heel Tracker/), file);
  await user.click(screen.getByRole('button', { name: /Extract Tracker text/ }));
  expect((await screen.findByRole('alert')).textContent).toContain('smaller than 10 MB');
  expect(fetch).not.toHaveBeenCalled();
});
