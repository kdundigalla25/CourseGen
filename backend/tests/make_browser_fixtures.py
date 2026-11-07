"""Generate only synthetic PDFs for browser tests; never copy private reference PDFs."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import make_pdf

root = Path(__file__).resolve().parents[2]
target = root / 'frontend' / 'e2e' / 'generated'
target.mkdir(parents=True, exist_ok=True)
for year in (2024,2026):
    data = json.loads((Path(__file__).parent / 'fixtures' / f'cohort_{year}.json').read_text(encoding='utf-8'))
    if year == 2026:
        # Browser-only scenario adds an explicitly synthetic unmet public label
        # to exercise the suggestion path; parser regression fixtures stay unchanged.
        i = data['pages'][0].index('∆\u00a0Not Satisfied: Ways of Knowing')
        data['pages'][0].insert(i, '∆\u00a0Not Satisfied: Engagement with the Human Past')
    pages = [[line.replace('∆\u00a0','??').replace('·','?') for line in page] for page in data['pages']]
    (target / f'synthetic-{year}.pdf').write_bytes(make_pdf(pages))
