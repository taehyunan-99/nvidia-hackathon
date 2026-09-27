"""Resolve supplied PDB references; never treat parent provenance as sequence identity."""
from dataclasses import replace
import hashlib
import math
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import gemmi
import requests

from . import structures

PDB_ID = re.compile(r'[1-9][A-Z0-9]{3}')
MAX_BYTES = 20 * 1024 * 1024


class SequenceMismatch(ValueError):
    """A valid search hit can belong to another target."""


def discover(heavy: str, work_dir: Path) -> list[str]:
    """A bounded exact-sequence search supplies candidates, never verified matches."""
    query = {'query': {'type': 'terminal', 'service': 'sequence', 'parameters': {
        'value': heavy, 'sequence_type': 'protein', 'identity_cutoff': 1.0, 'evalue_cutoff': 0.1}},
        'return_type': 'entry', 'request_options': {
            'paginate': {'start': 0, 'rows': 5}, 'results_content_type': ['experimental']}}
    record = {'query': query, 'http_status': None, 'response': None}
    try:
        response = requests.post('https://search.rcsb.org/rcsbsearch/v2/query', json=query,
                                 timeout=(5, 15), allow_redirects=False)
        record['http_status'] = response.status_code
        if response.status_code == 204:
            data, ids = None, []
        elif response.status_code == 200 and len(response.content) <= 1024 * 1024:
            data = response.json()
            record['response'] = data
            if not isinstance(data, dict):
                raise ValueError('자동 구조 검색 응답 형식을 확인하지 못했다.')
            total = data.get('total_count')
            results = data.get('result_set', [])
            if type(total) is not int or total < 0 or not isinstance(results, list):
                raise ValueError('자동 구조 검색 응답 형식을 확인하지 못했다.')
            if total > 4:
                raise ValueError('자동 검색 후보가 4개를 넘는다. PDB 번호를 지정해 확인해야 한다.')
            ids = [r.get('identifier') for r in results if isinstance(r, dict)]
            if len(ids) != total or any(not isinstance(i, str) or not PDB_ID.fullmatch(i) for i in ids) or len(set(ids)) != total:
                raise ValueError('자동 검색 결과가 불완전하거나 구조 번호가 유효하지 않다.')
        else:
            raise ValueError(f'자동 구조 검색 실패: HTTP {response.status_code}. 구조 부재로 단정하지 않는다.')
    except requests.RequestException as exc:
        record['error'] = type(exc).__name__
        raise ValueError('자동 구조 검색 통신 실패. 구조 부재로 단정하지 않는다.') from exc
    finally:
        work_dir.mkdir(parents=True, exist_ok=True)
        path = work_dir / f'pdb-search-{hashlib.sha256(heavy.encode()).hexdigest()}.json'
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return sorted(ids)


def source_ids(sources: list[dict]) -> list[str]:
    ids = set()
    for source in sources:
        record = (source.get('record_id') or '').strip().upper()
        url = urlsplit(source.get('url') or '')
        path = url.path.rstrip('/')
        from_url = None
        if url.hostname in {'www.rcsb.org', 'rcsb.org', 'files.rcsb.org'}:
            match = re.fullmatch(r'/(?:structure/([1-9a-zA-Z0-9]{4})|(?:download|view)/([1-9a-zA-Z0-9]{4})\.cif)', path)
            if url.scheme != 'https' or url.username or url.password or url.port not in {None, 443} or not match:
                raise ValueError('PDB 출처 URL 형식을 확인해야 한다.')
            from_url = next(v for v in match.groups() if v).upper()
            if not PDB_ID.fullmatch(from_url) or (record and record != from_url):
                raise ValueError('PDB 출처의 번호와 URL이 서로 다르다.')
        if PDB_ID.fullmatch(record):
            if source.get('url') and from_url != record:
                raise ValueError('PDB 번호의 출처가 공식 RCSB URL과 일치하지 않는다.')
            ids.add(record)
        elif from_url:
            ids.add(from_url)
    if len(ids) > 4:
        raise ValueError('후보 하나의 PDB 출처 조회는 최대 4개다.')
    return sorted(ids)


def download(pdb_id: str) -> bytes:
    # Only this constructed host/path is requested; user URLs and redirects are not followed.
    with requests.get(f'https://files.rcsb.org/download/{pdb_id}.cif',
                      timeout=(5, 20), stream=True, allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError(f'공개 구조 조회 실패: HTTP {response.status_code}. 구조 부재로 단정하지 않는다.')
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('공개 구조 파일이 조회 크기 제한을 넘었다.')
            chunks.append(chunk)
        return b''.join(chunks)


def public_structure(pdb_id: str, work_dir: Path) -> structures.PublicStructure:
    local = structures.load_catalog().get(pdb_id)
    if local:
        if structures.file_sha256(local.path) != local.verified_sha256:
            raise ValueError('공개 구조 파일의 해시가 검증된 원본과 다르다.')
        return local
    directory = work_dir / 'source-structures'
    directory.mkdir(parents=True, exist_ok=True)
    path, lock = directory / f'{pdb_id}.cif', directory / f'{pdb_id}.sha256'
    if path.exists() or lock.exists():
        if not path.is_file() or not lock.is_file() or structures.file_sha256(path) != lock.read_text().strip():
            raise ValueError('출처 조회 캐시의 파일 무결성이 맞지 않는다.')
        content = path.read_bytes()
    else:
        try:
            content = download(pdb_id)
        except requests.RequestException as exc:
            raise ValueError('공개 구조 조회 통신 실패. 구조 부재로 단정하지 않는다.') from exc
    block = gemmi.cif.read_string(content.decode('utf-8')).sole_block()
    if (block.find_value('_entry.id') or '').upper() != pdb_id:
        raise ValueError('요청한 PDB 번호와 받은 구조의 식별자가 다르다.')
    methods = [gemmi.cif.as_string(v).upper() for v in block.find_values('_exptl.method')]
    if not methods or any('THEORETICAL' in method for method in methods):
        raise ValueError('실험 구조 출처를 확인하지 못했다.')
    entities, glycans = structures.parse_entities(content.decode('utf-8'))
    digest = hashlib.sha256(content).hexdigest()
    if not path.exists():
        path.write_bytes(content)
        lock.write_text(digest + '\n')
    return structures.PublicStructure(pdb_id, path, f'https://files.rcsb.org/download/{pdb_id}.cif', digest, entities, glycans)


def match_public(public, heavy, light, target):
    block = gemmi.cif.read_file(str(public.path)).sole_block()
    polymers = {row[0]: structures.sequence_body(gemmi.cif.as_string(row[1]))
                for row in block.find('_entity_poly.', ['entity_id', 'pdbx_seq_one_letter_code_can'])}
    asym = {r[0]: r[1] for r in block.find('_struct_asym.', ['id', 'entity_id'])}
    rows = [list(r) for r in block.find('_atom_site.', ['label_asym_id', 'label_entity_id', 'label_seq_id',
                     'label_comp_id', 'Cartn_x', 'Cartn_y', 'Cartn_z', 'pdbx_PDB_model_num', 'auth_asym_id',
                     'occupancy', 'label_alt_id'])]
    if not rows or {r[7] for r in rows} != {'1'}:
        raise ValueError('좌표가 없거나 모델이 여러 개여서 자동 선택할 수 없다.')
    entities = {role: [eid for eid, seq in polymers.items() if
                      (bool(expected) and seq.find(expected) >= 0 and seq.find(expected, seq.find(expected) + 1) < 0
                       if role == 'target' else seq == expected)]
                for role, expected in [('target', target), ('heavy', heavy), ('light', light)]}
    def entity(role):
        found = entities[role]
        if len(found) != 1:
            return None
        eid = found[0]
        return structures.PolymerEntity(eid, role, polymers[eid], tuple(k for k,v in asym.items() if v == eid))
    h, l, t = entity('heavy'), entity('light'), entity('target')
    match = structures.StructureMatch(public.pdb_id, h, l, t, h is not None, l is not None, public=public)
    if len(entities['heavy']) > 1 or len(entities['light']) > 1:
        raise ValueError('후보 서열에 일치하는 entity가 여러 개여서 자동 선택할 수 없다.')
    if not entities['target']:
        # Exact H/L sequences and no other polymer establish antibody-only
        # provenance. Repeated copies need no coordinate selection here.
        if h and l and h.entity_id != l.entity_id and set(polymers) == {h.entity_id, l.entity_id}:
            return replace(match, notes=(
                f'{public.pdb_id}: 중쇄·경쇄 기탁 서열이 모두 일치하는 항체 단독 구조다. '
                'HER2 복합체 좌표는 없으므로 서열 출처로만 사용하며, 복합체는 별도 예측이 필요하다.',))
        raise SequenceMismatch('입력 HER2 구간과 구조 표적 서열이 일치하지 않는다. 항체 단독 출처로도 확인되지 않았다.')
    if len(entities['target']) != 1:
        raise ValueError('입력 HER2 구간과 구조 표적 서열의 유일한 대응을 확인하지 못했다.')
    if not match.complete:
        return replace(match, notes=(f'{public.pdb_id}: 후보 서열 불일치. 부모 서열 출처일 수 있으나 후보의 실험 구조로 재사용하지 않는다.',))
    # Preserve the already reviewed local catalog's chain choice. Newly retrieved
    # entries must have a unique label chain for each role; no first-copy selection.
    local = structures.load_catalog().get(public.pdb_id)
    mapping, ranges, notes = [], [], []
    calculation_hold = None
    for role, e, expected in [('target',t,target),('heavy',h,heavy),('light',l,light)]:
        chains = list(e.strand_ids)
        if local:
            reviewed = next((x for x in local.by_role(role) if x.entity_id == e.entity_id), None)
            chains = [reviewed.strand_ids[0]] if reviewed and reviewed.strand_ids else []
        if len(chains) != 1 or asym.get(chains[0]) != e.entity_id:
            raise ValueError(f'{role} 사슬 복사체가 여러 개이거나 대응이 불명확해 보류한다.')
        chain = chains[0]
        selected = [r for r in rows if r[0] == chain]
        if not selected or len({r[8] for r in selected}) != 1:
            raise ValueError(f'{role} 사슬의 좌표 또는 author 대응이 불명확하다.')
        offset = e.sequence.index(expected)
        for r in selected:
            n = int(r[2])
            if r[1] != e.entity_id or not 1 <= n <= len(e.sequence):
                raise ValueError('좌표의 entity·잔기 번호 대응이 다르다.')
            if gemmi.find_tabulated_residue(r[3]).one_letter_code.upper() != e.sequence[n-1]:
                raise ValueError('좌표의 잔기 종류가 기탁 서열과 다르다.')
            if not all(math.isfinite(float(v)) for v in r[4:7]):
                raise ValueError('구조에 유한하지 않은 좌표가 있다.')
            if offset < n <= offset + len(expected) and (float(r[9]) != 1 or r[10] not in {'.', '?'}):
                calculation_hold = '입력 구간에 부분 점유율·대체 좌표가 있어 접촉 계산에 쓸 원자를 자동 선택하지 않았다.'
        mapping.append({'role':role,'model_number':1,'label_asym_id':chain,'auth_asym_id':selected[0][8],'operator_id':None})
        ranges.append((chain, offset+1, offset+len(expected)))
        if len(e.sequence) != len(expected):
            notes.append(f'{role}: 기탁 {len(e.sequence)}잔기 중 입력 {len(expected)}잔기만 계산한다. 원본 좌표 파일은 보존한다.')
    if len({m['label_asym_id'] for m in mapping}) != 3:
        raise ValueError('표적·중쇄·경쇄가 서로 다른 사슬에 대응해야 한다.')
    return replace(match, chain_mapping=tuple(mapping), residue_ranges=tuple(ranges), notes=tuple(notes),
                   calculation_hold_reason=calculation_hold)


def lookup(candidate: dict, target_fasta: str, work_dir: Path) -> structures.StructureMatch:
    empty = structures.StructureMatch(None,None,None,None,False,False)
    try:
        ids = source_ids(candidate.get('sources', []))
        search_notes = []
        automatic = False
        if not ids:
            legacy = structures.find_structure(candidate['heavy_chain_fasta'], candidate['light_chain_fasta'])
            if not legacy.complete and os.getenv('PDB_SEARCH_ENABLED', '1') == '1' and all(
                    len(structures.sequence_body(candidate[f'{role}_chain_fasta'])) >= 50 for role in ('heavy', 'light')):
                ids = discover(structures.sequence_body(candidate['heavy_chain_fasta']), work_dir)
                automatic = True
                search_notes.append(f'중쇄 서열의 제한된 자동 검색에서 구조 후보 {len(ids)}개를 찾았다. 전체 중쇄·경쇄와 표적은 파일에서 별도 검증한다.')
            if not ids:
                if not legacy.pdb_id:
                    return replace(legacy, notes=tuple(search_notes or ['로컬 구조 목록에서 일치 후보를 찾지 못했다. 전체 공개 자료의 부재를 뜻하지 않는다.']))
                ids = [legacy.pdb_id]
        matches, notes = [], []
        for pdb_id in ids:
            public = public_structure(pdb_id, work_dir)
            try:
                match = match_public(public, structures.sequence_body(candidate['heavy_chain_fasta']),
                                     structures.sequence_body(candidate['light_chain_fasta']), structures.sequence_body(target_fasta))
            except SequenceMismatch as exc:
                if not automatic:
                    raise
                notes.append(f'{pdb_id}: {exc}')
                continue
            matches.append(match)
            notes.extend(match.notes)
        if not matches:
            return replace(empty, notes=tuple(search_notes + notes))
        complete = [m for m in matches if m.complete]
        if len(complete) > 1:
            raise ValueError('일치하는 공개 구조가 여러 개다. 사용할 PDB 출처를 하나로 정해야 한다.')
        chosen = complete[0] if complete else max(matches, key=lambda m: m.heavy_exact + m.light_exact)
        return replace(chosen, notes=tuple(search_notes + notes))
    except (ValueError, RuntimeError, OSError, UnicodeError) as exc:
        return replace(empty, blocked_reason=f'출처 확인 보류: {exc}')
