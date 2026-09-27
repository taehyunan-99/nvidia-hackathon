"""Live transport regression; preserves the original benchmark, uses cached structures only."""
import json
import logging
from pathlib import Path
import shutil

import benchmark_agent as b

original_manifest, original_work = b.MANIFEST, b.WORK
b.MANIFEST = original_manifest.with_name('paced-agent-manifest.json')
b.RESULTS = original_manifest.with_name('paced-agent-results.jsonl')
b.WORK = original_work / 'paced'


def main():
    if b.RESULTS.exists():
        raise SystemExit('Already attempted: retain failures; do not silently rerun.')
    manifest = json.loads(original_manifest.read_text())
    manifest['parent_manifest_sha256'] = b.sha(original_manifest.read_bytes())
    manifest['code_sha256'] = {str(p.relative_to(b.ROOT)): b.sha(p.read_bytes()) for p in b.CODE}
    manifest['rules'] = ('Transport regression on the same eight cases. All attempts retained. '
                         'Cached Boltz structures; live Nemotron. 15-second request spacing; '
                         'at most three attempts on 429; no retry after partial stream. '
                         'Not a new held-out accuracy test.')
    b.write(b.MANIFEST, manifest)
    shutil.copytree(original_work / 'prediction-cache', b.WORK / 'prediction-cache', dirs_exist_ok=True)
    original_predict = b.RecordedClient.predict_complex

    def predict(self, *args, **kwargs):
        self.mode = 'rule'  # Fail closed on a cache miss: never purchase another structure prediction.
        return original_predict(self, *args, **kwargs)

    b.RecordedClient.predict_complex = predict
    logging.basicConfig(level=logging.INFO)
    for case in ['1N8Z', '1S78', 'missing-target', 'short-heavy', '8JYR', '3N85', 'invalid-char', 'invalid-range']:
        print('START_CASE', case, flush=True)
        b.run(case, 'nat')


if __name__ == '__main__':
    main()
