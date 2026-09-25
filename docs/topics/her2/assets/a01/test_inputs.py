import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch

import build_inputs as builder


class ReferenceInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = ''.join((builder.HERE / 'sources/P04626.fasta').read_text().splitlines()[1:])
        cls.entries = {pdb: builder.inspect_entry(pdb, cls.canonical) for pdb in builder.PDBS}
        cls.structures = json.loads((builder.OUT / 'structures.json').read_text(encoding='utf-8'))

    def test_rcsb_deposited_and_modeled_counts(self):
        expected = {'1N8Z': (7890, 1041, 1015, 26), '1S78': (15481, 2128, 1995, 133)}
        for pdb, (_, atoms, mapping, chains, _, _) in self.entries.items():
            observed = (len(atoms), sum(c['sequence_length'] or 0 for c in chains),
                        sum(r['has_coordinates'] for r in mapping if r['label_seq_id'] is not None),
                        sum(not r['has_coordinates'] for r in mapping))
            self.assertEqual(observed, expected[pdb])

    def test_reference_sequence_and_known_missing_segment(self):
        mapping = self.entries['1N8Z'][2]
        first = next(r for r in mapping if r['label_asym_id'] == 'C' and r['label_seq_id'] == 1)
        missing = next(r for r in mapping if r['label_asym_id'] == 'C' and r['label_seq_id'] == 102)
        self.assertEqual((first['auth_seq_id'], first['uniprot_position'], first['sequence_position']), (1, 23, 23))
        self.assertEqual((missing['auth_seq_id'], missing['uniprot_position'], missing['has_coordinates']), (102, 124, False))
        self.assertEqual(len(self.canonical), 1255)

    def test_pertuzumab_insertion_codes_are_distinct(self):
        chain = [r for r in self.entries['1S78'][2] if r['label_asym_id'] == 'D']
        self.assertEqual([(r['label_seq_id'], r['insertion_code']) for r in chain if r['auth_seq_id'] == 82],
                         [(83, None), (84, 'A'), (85, 'B'), (86, 'C')])
        self.assertEqual([(r['label_seq_id'], r['auth_seq_id']) for r in chain if not r['has_coordinates']],
                         [(223, 217), (224, 218), (225, 219), (226, 220)])

    def test_nonpolymer_author_chains_are_not_polymer_identity(self):
        nag = next(r for r in self.entries['1N8Z'][2] if r['label_asym_id'] == 'D')
        self.assertEqual((nag['auth_asym_id'], nag['auth_seq_id'], nag['label_seq_id'], nag['component_id']),
                         ('C', 766, None, 'NAG'))
        self.assertIsNone(nag['sequence_position'])
        components = [r['component_id'] for r in self.entries['1S78'][2] if r['label_seq_id'] is None]
        self.assertEqual(components.count('BMA'), 1)
        self.assertEqual(components.count('NAG'), 12)

    def test_separate_assemblies_and_service_sequence_basis(self):
        structures = {s['structure_id']: s for s in self.structures}
        first, second = structures['1s78-assembly-1'], structures['1s78-assembly-2']
        self.assertEqual({r['label_asym_id'] for r in first['chain_mapping']}, set('ACDGHL'))
        self.assertEqual({r['label_asym_id'] for r in second['chain_mapping']}, set('BEFIJKM'))
        self.assertEqual(first['candidate_id'], second['candidate_id'])
        position = next(r for r in first['residue_mapping'] if r['label_asym_id'] == 'A' and r['label_seq_id'] == 1)
        self.assertEqual(position['sequence_position'], 23)
        self.assertIsNone(first['alignment'])

    def test_wrong_target_sequence_is_rejected(self):
        wrong = self.canonical[:22] + 'X' + self.canonical[23:]
        with self.assertRaisesRegex(ValueError, 'UniProt sequence mismatch'):
            builder.inspect_entry('1N8Z', wrong)

    def test_wrong_author_number_is_rejected(self):
        changed = copy.deepcopy(self.entries['1S78'][0])
        index = next(i for i, (chain, pos) in enumerate(zip(changed['_atom_site.label_asym_id'],
                                                         changed['_atom_site.label_seq_id']))
                     if chain == 'D' and pos == '84')
        changed['_atom_site.auth_seq_id'][index] = '999'
        with patch.object(builder, 'MMCIF2Dict', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'numbering'):
                builder.inspect_entry('1S78', self.canonical)

    def test_missing_annotation_removal_is_rejected(self):
        changed = copy.deepcopy(self.entries['1N8Z'][0])
        for key in changed:
            if key.startswith('_pdbx_unobs_or_zero_occ_residues.'):
                changed[key] = changed[key][1:]
        with patch.object(builder, 'MMCIF2Dict', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'missing residue not annotated'):
                builder.inspect_entry('1N8Z', self.canonical)

    def test_generated_outputs_are_reproducible(self):
        paths = [p for p in builder.OUT.iterdir() if p.name != 'validation.json']
        before = {p.name: builder.digest(p) for p in paths}
        with contextlib.redirect_stdout(io.StringIO()):
            builder.main()
        self.assertEqual(before, {p.name: builder.digest(p) for p in paths})


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceInputTests)
    names = [test.id().split('.')[-1] for test in suite]
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    builder.write_json('validation.json', {
        'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests_run': result.testsRun,
        'tests': names, 'failures': [(test.id(), reason) for test, reason in result.failures],
        'errors': [(test.id(), reason) for test, reason in result.errors],
        'evidence_basis': 'RCSB entry counts, inspected mmCIF residue anchors, corruption rejection, offline rebuild',
    })
    print(f'{"PASS" if result.wasSuccessful() else "FAIL"}: {result.testsRun} A-01 checks; generated/validation.json')
    if not result.wasSuccessful():
        print(stream.getvalue())
    raise SystemExit(0 if result.wasSuccessful() else 1)
