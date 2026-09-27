"""Separate completed agent tasks, recovered HTTP errors, and unchanged structure accuracy."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'pyproject.toml').exists())


def main():
    generated = HERE / 'generated'
    manifest = json.loads((generated / 'paced-agent-manifest.json').read_text())
    original = json.loads((generated / 'agent-benchmark-manifest.json').read_text())
    assert manifest['cases'] == original['cases']
    digest = hashlib.sha256((generated / 'paced-agent-manifest.json').read_bytes()).hexdigest()
    rows = [json.loads(line) for line in (generated / 'paced-agent-results.jsonl').read_text().splitlines()]
    assert len(rows) == len({r['id'] for r in rows}) == 8
    assert all(r['manifest_sha256'] == digest and r['network_predictions'] == 0 for r in rows)
    calls, skipped, current = {}, Counter(), None
    for line in (ROOT / 'work/agent-benchmark/paced.log').read_text().splitlines():
        if line.startswith('START_CASE '):
            current = line.split()[-1]
            calls[current] = []
        if 'nim_http ' in line:
            calls[current].append(json.loads(line.split('nim_http ', 1)[1]))
        if 'nim_terminal_no_request' in line:
            skipped[current] += 1
    cases = {c['id']: c for c in manifest['cases']}
    measured = [r for r in rows if cases[r['id']]['model_required']]
    http = [c for batch in calls.values() for c in batch]
    starts = [datetime.fromisoformat(c['started_at']) for c in http]
    gaps = [(b-a).total_seconds() for a, b in zip(starts, starts[1:])]
    result = {'cases': len(rows), 'model_required_cases': len(measured),
              'agent_task_success': sum(r['agent_task_success'] for r in measured),
              'no_unhandled_error_success': sum(r['clean_success'] for r in measured),
              'fallbacks': sum(r['fallback_used'] for r in measured),
              'successful_cases_without_http_errors': sum(r['clean_success'] and all(c['status'] == 200 for c in calls[r['id']]) for r in measured),
              'final_output_correct': sum(r['output_correct'] for r in rows),
              'http_status_counts': dict(Counter(c['status'] for c in http)),
              'minimum_request_gap_seconds': min(gaps) if gaps else None,
              'terminal_requests_skipped': sum(skipped.values()),
              'new_boltz_calls': sum(r['network_predictions'] for r in rows),
              'prediction_cache_hits': sum(r['prediction_cache_hits'] for r in rows),
              'per_case': [{**r, 'http': calls[r['id']], 'terminal_requests_skipped': skipped[r['id']]} for r in rows],
              'limitations': 'Same-case transport regression, not held-out accuracy. Recovered 429s still count as HTTP errors. Cached structures do not improve biological accuracy. Before/after runs at different times cannot isolate the causal effect of pacing.'}
    path = generated / 'paced-agent-summary.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'per_case'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
