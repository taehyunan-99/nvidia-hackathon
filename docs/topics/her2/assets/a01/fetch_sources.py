import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def main():
    lock_path = HERE / 'source-lock.json'
    previous = json.loads(lock_path.read_text(encoding='utf-8')) if lock_path.exists() else None
    expected = {s['path']: s['sha256'] for s in previous['sources']} if previous else {}
    urls = {
        (HERE / 'sources' / f'{pdb}.cif').relative_to(ROOT).as_posix():
        f'https://files.rcsb.org/download/{pdb}.cif'
        for pdb in ('1N8Z', '1S78')
    }
    for pdb, assemblies in (('1N8Z', ('1',)), ('1S78', ('1', '2'))):
        for assembly in assemblies:
            name = f'{pdb}-assembly{assembly}.cif'
            urls[(HERE / 'sources' / name).relative_to(ROOT).as_posix()] = (
                f'https://files.rcsb.org/download/{name}'
            )
    urls[(HERE / 'sources/P04626.fasta').relative_to(ROOT).as_posix()] = (
        'https://rest.uniprot.org/uniprotkb/P04626.fasta'
    )
    snapshots = []
    for relative, url in urls.items():
        request = Request(url, headers={'User-Agent': 'HER2-A01-reference-audit/1.0'})
        with urlopen(request, timeout=60) as response:
            payload = response.read()
        digest = hashlib.sha256(payload).hexdigest()
        path = ROOT / relative
        if relative in expected and digest != expected[relative]:
            raise ValueError(f'Upstream changed: {relative}; review before replacing snapshot')
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f'Local file differs from upstream: {relative}; preserved')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(payload)
        snapshots.append({'path': relative, 'url': url, 'sha256': digest, 'bytes': len(payload)})
    if not previous:
        lock_path.write_text(json.dumps({
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'sources': snapshots,
        }, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(snapshots)} public source files verified; existing snapshots preserved')


if __name__ == '__main__':
    main()
