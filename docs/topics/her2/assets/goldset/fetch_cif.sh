#!/usr/bin/env bash
# 평가셋 10건의 mmCIF를 RCSB에서 받는다. 약 9MB라 저장소에 넣지 않는다.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$here/cif"
for id in 3BE1 3WSQ 5O4G 6ATT 6BGT 9L1S 9T3R 9T3S 4P59 8YRY; do
  if [ -s "$here/cif/$id.cif" ]; then
    echo "이미 있음 $id"
    continue
  fi
  echo "받는 중 $id"
  curl -fsS -o "$here/cif/$id.cif" "https://files.rcsb.org/download/$id.cif"
done
echo "완료: $here/cif"
