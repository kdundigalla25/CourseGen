"""Generate the frontend contract without running a server."""
import json
from pathlib import Path
from app.main import app

Path(__file__).with_name("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
