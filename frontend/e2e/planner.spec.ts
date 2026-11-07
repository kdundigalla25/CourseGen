import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';
import { readFile } from 'node:fs/promises';

for (const year of [2024,2026]) test(`${year} synthetic Tracker to preferred calendar and exports`,async ({page},testInfo) => {
  await page.goto('/');
  await page.getByLabel(/Choose your Tar Heel Tracker/).setInputFiles(resolve(`e2e/generated/synthetic-${year}.pdf`));
  await page.getByRole('button',{name:/Extract Tracker text/}).click();
  await page.getByLabel(/I've checked my details against my Tracker/).check();
  await page.getByRole('button',{name:'Use this progress',exact:true}).click();
  await page.getByLabel('Semester and course data').selectOption(JSON.stringify(['fictional-demo-v1','sample-spring-2027']));
  if(year===2026) await page.getByRole('button',{name:'Add DEMO 101',exact:true}).click();
  else {
    await page.getByLabel('Course code or title').fill('DEMO 101');
    await page.getByRole('button',{name:'Search courses',exact:true}).click();
    await page.getByRole('button',{name:'Add from search DEMO 101',exact:true}).click();
  }
  await page.getByLabel('Must include DEMO 101').check();
  await page.getByLabel('Target credits').fill('3');
  await page.getByRole('button',{name:'Generate schedules',exact:true}).click();
  await expect(page.getByRole('region',{name:'Compare schedules',exact:true})).toBeVisible();
  const event=page.getByRole('button',{name:/Option 1: DEMO 101, section A/});
  await event.focus();
  await expect(event).toBeFocused();
  await event.press('Enter');
  await expect(page.getByRole('status').filter({hasText:/DEMO 101.*Section A/})).toBeVisible();
  await expect(page.getByRole('button',{name:'Download schedule JSON'})).toBeDisabled();
  await page.getByRole('combobox',{name:'Compare with',exact:true}).selectOption('1');
  await expect(page.getByRole('region',{name:'Option 2 weekly calendar',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Use option 2 as preferred',exact:true}).click();
  await page.getByRole('combobox',{name:'View option',exact:true}).selectOption('0');
  await expect(page.getByRole('heading',{name:'Keep preferred option 2',exact:true})).toBeVisible();
  for(const format of ['JSON','ICS']) {
    const download=page.waitForEvent('download');
    await page.getByRole('button',{name:format==='JSON' ? 'Download schedule JSON' : 'Download calendar ICS',exact:true}).click();
    const file=await download;
    const content=await readFile((await file.path())!,'utf8');
    if(format==='JSON') {
      const data=JSON.parse(content);
      expect(data.schedule.courses[0].sections[0].number).toBe('B');
      expect(data.reviewed).toBeUndefined();
      expect(data.classification).toBe('fictional');
    } else {
      expect(content).toContain('BEGIN:VEVENT');
      expect(content).toContain('DTSTART:202701');
      expect(content).toContain('Not official UNC');
    }
  }
  await page.emulateMedia({media:'print'});
  await expect(page.locator('.print-sheet')).toBeVisible();
  await expect(page.locator('.print-sheet')).toContainText('Preferred option 2');
  await expect(page.locator('main')).toBeHidden();
  await page.emulateMedia({media:'screen'});
  const calendar=page.getByRole('region',{name:'Compare schedules',exact:true});
  await calendar.screenshot({path:testInfo.outputPath('calendar.png')});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByLabel('Avoid Monday').check();
  await expect(calendar).toHaveCount(0);
  await expect(page.locator('.print-sheet')).toHaveCount(0);
  for(const day of ['Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']) await page.getByLabel(`Avoid ${day}`).check();
  await page.getByRole('button',{name:'Generate schedules',exact:true}).click();
  await expect(page.getByRole('heading',{name:'No schedule found',exact:true})).toBeVisible();
  await page.getByLabel('Starting term',{exact:true}).fill(`${year} Fall `);
  await expect(page.getByLabel('Semester and course data')).toHaveCount(0);
});
