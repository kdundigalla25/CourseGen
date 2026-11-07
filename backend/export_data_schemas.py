"""Regenerate public import contracts after changing domain models."""
import json
from pathlib import Path

from app.catalog_models import CatalogSnapshot
from app.rule_models import GenEdRulePack, ProgramRulePack

directory = Path(__file__).resolve().parents[1] / 'data' / 'schemas'
directory.mkdir(parents=True, exist_ok=True)
for name, model in [('catalog-snapshot', CatalogSnapshot), ('gen-ed-rule-pack', GenEdRulePack), ('program-rule-pack', ProgramRulePack)]:
    (directory / f'{name}.schema.json').write_text(json.dumps(model.model_json_schema(), indent=2) + '\n', encoding='utf-8')
