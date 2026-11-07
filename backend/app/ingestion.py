"""Manual, validated JSON import. No web requests and no student-document storage."""
import argparse
import hashlib
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.catalog_models import CatalogSnapshot
from app.curriculum import DATA_ROOT


def validate_file(path: Path) -> CatalogSnapshot:
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Catalog import exceeds 10 MB')
    return CatalogSnapshot.model_validate_json(path.read_text(encoding='utf-8'))


def publish_snapshot(snapshot: CatalogSnapshot, directory: Path) -> Path:
    # Revalidate even for callers holding a mutated Pydantic object.
    snapshot = CatalogSnapshot.model_validate(snapshot.model_dump(mode='json'))
    content = (snapshot.model_dump_json(indent=2) + '\n').encode('utf-8')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{snapshot.id}.json'
    if target.exists():
        previous = validate_file(target)
        if previous != snapshot:
            raise ValueError('Published snapshot IDs are immutable; use a new ID for changed data')
        return target
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.catalog-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        # Atomic complete-file publication without replacing an existing snapshot.
        # Concurrent writers cannot overwrite a previously published ID.
        try:
            os.link(temporary, target)
        except FileExistsError:
            if validate_file(target) != snapshot:
                raise ValueError('A different snapshot already uses this ID') from None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'publish'])
    parser.add_argument('file', type=Path)
    parser.add_argument('--directory', type=Path, default=DATA_ROOT / 'published')
    args = parser.parse_args()
    try:
        snapshot = validate_file(args.file)
        canonical = snapshot.model_dump_json().encode('utf-8')
        print(f'Valid {snapshot.classification} snapshot: {snapshot.id}; {len(snapshot.courses)} course editions, {len(snapshot.sections)} sections, {len(snapshot.bundles)} bundles')
        print('SHA256:', hashlib.sha256(canonical).hexdigest())
        if args.command == 'publish':
            print('Published:', publish_snapshot(snapshot, args.directory))
        return 0
    except ValidationError as exc:
        for issue in exc.errors(include_input=False):
            print('Invalid:', '.'.join(str(part) for part in issue['loc']) or 'snapshot', '-', issue['msg'])
    except (OSError, ValueError) as exc:
        print(f'Import failed: {exc}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
