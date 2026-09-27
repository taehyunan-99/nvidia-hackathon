"""All-atom contact validation with pinned Richardson Lab Reduce and Probe.

Uses the CCTBX clashscore selections (electron-cloud H, no heavy-atom flips,
bad overlaps >= 0.4 A, hydrogen bonds excluded). Original mmCIF is untouched.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import gemmi

from .analysis import Measurement
from .surface_analysis import rows

REDUCE_REV = '3cef69cecc8e5fcfff236a2e64166cce601e5e0c'
PROBE_REV = '835c2c63dd14b8c30599900b07c2296925cc933c'


def prepare(text, mapping, residues, context_chains):
    allowed = {(r['label_asym_id'], r['label_seq_id']) for r in residues if r['has_coordinates']}
    roles = {r['label_asym_id']: r['role'] for r in mapping if r['role'] != 'context'}
    labels = list(roles) + sorted(context_chains)
    if len(labels) > 26 or len(set(labels)) != len(labels):
        raise ValueError('고유 사슬을 분석용 PDB에 대응할 수 없다.')
    structure = gemmi.Structure()
    model = gemmi.Model('1')
    index, seen = {}, set()
    raw = rows(gemmi.cif.read_string(text).sole_block(), '_atom_site')
    for label, new_chain in zip(labels, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
        chain = gemmi.Chain(new_chain)
        groups = {}
        for r in raw:
            if r['pdbx_PDB_model_num'] != '1' or r['label_asym_id'] != label or r['type_symbol'] in {'H', 'D'}:
                continue
            number = int(r['label_seq_id']) if r['label_seq_id'].isdigit() else None
            if label in roles and (label, number) not in allowed:
                continue
            if r['type_symbol'] not in {'C', 'N', 'O', 'S'} or float(r['occupancy']) != 1 or r['label_alt_id'] not in {'.', '?'}:
                raise ValueError('미지원 원소·부분 점유율·대체 좌표는 충돌 계산하지 않는다.')
            if label in context_chains and r['label_comp_id'] != 'NAG':
                raise ValueError('검증되지 않은 당 성분이다.')
            key = (number, r.get('auth_seq_id', '?'), r.get('pdbx_PDB_ins_code', '?'), r['label_comp_id'])
            atom_key = (label, key, r['label_atom_id'])
            if atom_key in seen:
                raise ValueError('중복 원자 identity다.')
            seen.add(atom_key)
            if key not in groups:
                res = gemmi.Residue()
                res.name, res.seqid = r['label_comp_id'], gemmi.SeqId(number if label in roles else len(groups) + 1, ' ')
                if not 1 <= res.seqid.num <= 9999:
                    raise ValueError('분석용 PDB 잔기 번호 범위를 넘었다.')
                res.het_flag = 'H' if label in context_chains else 'A'
                groups[key] = res
                original = {'model_number': 1, 'label_asym_id': label, 'auth_asym_id': r.get('auth_asym_id'),
                    'label_seq_id': number, 'auth_seq_id': int(key[1]) if key[1].lstrip('-').isdigit() else None,
                    'insertion_code': None if key[2] in {'.', '?'} else key[2], 'sequence_position': None,
                    'has_coordinates': True, 'operator_id': None}
                index[(new_chain, res.seqid.num)] = {'residue': original, 'role': roles.get(label, 'context')}
            atom = gemmi.Atom()
            atom.name, atom.element = r['label_atom_id'], gemmi.Element(r['type_symbol'])
            atom.pos = gemmi.Position(*(float(r[f'Cartn_{a}']) for a in 'xyz'))
            atom.occ, atom.b_iso = 1, 0
            groups[key].add_atom(atom)
        for res in groups.values():
            chain.add_residue(res)
        model.add_chain(chain)
    structure.add_model(model)
    return structure.make_pdb_string(), index


def parse_contacts(output):
    bad, hbonds = {}, set()
    for line in output.splitlines():
        fields = line.split(':')
        if len(fields) < 8:
            continue
        kind = fields[2]
        pair = tuple(sorted((fields[3], fields[4])))
        if kind == 'hb':
            hbonds.add(pair)
        elif kind == 'bo' and float(fields[7]) <= -0.4:
            bad[pair] = min(float(fields[7]), bad.get(pair, 0))
    return {pair: gap for pair, gap in bad.items() if pair not in hbonds}


def _heavy(text):
    return sorted(line[12:27] + line[30:54] for line in text.splitlines()
                  if line.startswith(('ATOM  ', 'HETATM')) and line[76:78].strip() not in {'H', 'D'})


def calculate(text, mapping, residues, context_chains, work_dir, source):
    reduce = os.getenv('REDUCE_BIN') or shutil.which('reduce')
    probe = os.getenv('PROBE_BIN') or shutil.which('probe')
    dictionary = os.getenv('REDUCE_HET_DICT')
    if not reduce or not probe or not dictionary or not Path(dictionary).is_file():
        return Measurement.not_run('atom_clash', '검증된 Reduce·Probe와 원자 사전이 없어 정식 충돌 검사를 실행하지 않았다.')
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    execution = []
    def command(args, content):
        p = subprocess.run(args, input=content, text=True, capture_output=True, timeout=120)
        execution.append({'tool': Path(args[0]).name, 'arguments': args[1:], 'returncode': p.returncode})
        # Standalone Reduce returns -1 for trim, and 1 when a clique needs zero
        # adjustments as well as when it is abandoned. Unlike its Python wrapper,
        # inspect diagnostics and reject every abandoned/failed optimization.
        allowed = {0, 255} if '-trim' in args else ({0, 1} if args[0] == reduce else {0})
        if p.returncode not in allowed or any(word in p.stderr.lower() for word in ('error', 'abandoned', 'failed to initialize')):
            raise ValueError(f'{Path(args[0]).name} 실행 실패 (exit {p.returncode})')
        if args[0] == reduce and not p.stdout.startswith('USER  MOD reduce.'):
            raise ValueError('Reduce 산출물 머리말이 없다.')
        (root / f'command-{len(execution)}.log').write_text(p.stderr)
        return p.stdout
    try:
        pdb, index = prepare(text, mapping, residues, context_chains)
        trimmed = command([reduce, '-quiet', '-trim', '-'], pdb)
        hydrogenated = command([reduce, '-DB', dictionary, '-oh', '-his', '-flip', '-keep', '-allalt', '-limit10', '-pen9999', '-'], trimmed)
        if _heavy(pdb) != _heavy(hydrogenated):
            raise ValueError('수소 배치 과정에서 원래 중원자 좌표·identity가 바뀌었다.')
        if not any(l.startswith(('ATOM  ', 'HETATM')) and l[76:78].strip() == 'H' for l in hydrogenated.splitlines()):
            raise ValueError('분석에 필요한 수소를 배치하지 못했다.')
        output = command([probe, '-u', '-q', '-mc', '-het', '-once', '-NOVDWOUT', '-CON', 'ogt10 not water', 'ogt10', '-'], hydrogenated)
        counts = command([probe, '-q', '-mc', '-het', '-dumpatominfo', 'ogt10 not water', '-'], hydrogenated)
        atom_count = int(counts.strip().split(':')[-1])
        if atom_count <= 0:
            raise ValueError('분석 원자 수가 없다.')
        clashes = parse_contacts(output)
        interface, highlighted = [], {}
        for pair, gap in clashes.items():
            identities = [(atom[:2].strip(), int(atom[2:6])) for atom in pair]
            entries = [index[k] for k in identities]
            selected_roles = {e['role'] for e in entries}
            if selected_roles & {'heavy', 'light'} and selected_roles & {'target', 'context'}:
                interface.append({'atoms': list(pair), 'overlap_angstrom': -gap})
                for k, entry in zip(identities, entries):
                    highlighted[k] = entry['residue']
        metadata = {'reduce_revision': REDUCE_REV, 'probe_revision': PROBE_REV, 'execution': execution,
            'input_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'analysis_pdb_sha256': hashlib.sha256(hydrogenated.encode()).hexdigest(),
            'atom_count': atom_count, 'whole_structure_clash_count': len(clashes),
            'whole_structure_clashscore': len(clashes) * 1000 / atom_count,
            'interface_clashes': interface,
            'residue_mapping': [{'analysis_chain': k[0], 'analysis_number': k[1], **v} for k, v in index.items()]}
        (root / 'hydrogenated.pdb').write_text(hydrogenated)
        (root / 'probe-contacts.txt').write_text(output)
        (root / 'clashes.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        return Measurement(topic='atom_clash', kind='computed', state='measured', value=len(interface),
            unit='atom_pair', residues=list(highlighted.values()), sources=[source, {
                'title': 'Richardson Lab Reduce / Probe', 'url': 'https://github.com/rlabduke/probe', 'record_id': PROBE_REV}],
            definition=f'Reduce 4.16·Probe 2.26: 수소를 배치한 관측 구조의 항체–표적/포함 당 사이 비결합 겹침 ≥0.4 Å 원자쌍. 수소결합 제외, 중원자 flip 금지. '
            f'전체 구조 clashscore {metadata["whole_structure_clashscore"]:.4f} ({len(clashes)}쌍/{atom_count}원자×1000)와 구별. '
            '분석 복사본은 0.001 Å 정밀도의 PDB이며 전체 접근성·효능 판정이 아니다.')
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return Measurement(topic='atom_clash', kind='computed', state='failed', reason=f'정식 충돌 검사 실패: {exc}', sources=[source])
