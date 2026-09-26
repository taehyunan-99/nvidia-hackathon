import contextlib
import copy
import csv
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

import compare as a03


def glycan(xyz=(3, 0, 0), author=1, insertion=None):
    return {'model_number': 1, 'operator_id': '1', 'assembly_id': '1',
            'label_asym_id': 'G', 'auth_asym_id': 'G', 'label_seq_id': None,
            'sequence_position': None, 'auth_seq_id': author, 'insertion_code': insertion,
            'component': 'NAG', 'atom_name': 'C1', 'element': 'C', 'xyz': xyz}


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.protein = [a03.metrics.Coordinate('A', 1, 'CA', 'C', (0, 0, 0))]

    def test_analytic_spherical_cap_protein_only(self):
        result = a03.compare(self.protein, [glycan()], 20000)
        radius = 1.7 + 1.4
        sphere = 4 * math.pi * radius ** 2
        cap = 2 * math.pi * radius * (radius - 3 / 2)
        self.assertAlmostEqual(result['core'][('A', 1)], sphere, places=9)
        self.assertAlmostEqual(result['reduction'][('A', 1)], cap, delta=0.15)
        self.assertAlmostEqual(result['context'][('A', 1)], sphere - cap, delta=0.15)
        self.assertEqual(set(result['context']), {('A', 1)})

    def test_distant_observed_glycan_is_measured_zero(self):
        result = a03.compare(self.protein, [glycan((100, 0, 0))])
        self.assertEqual(result['state'], 'measured')
        self.assertEqual(result['reduction'][('A', 1)], 0)

    def test_absent_context_or_protein_is_unknown(self):
        for protein, context in ((self.protein, []), ([], [glycan()])):
            result = a03.compare(protein, context)
            self.assertEqual(result['state'], 'unknown')
            self.assertIsNone(result['reduction'])

    def test_author_number_and_insertion_keep_sugars_distinct(self):
        atoms = [glycan(), glycan((-3, 0, 0), 2), glycan((0, 3, 0), 2, 'A')]
        a03.validate_glycans(atoms)
        result = a03.compare(self.protein, atoms)
        one = a03.compare(self.protein, atoms[:1])
        self.assertGreater(result['reduction'][('A', 1)], one['reduction'][('A', 1)])
        self.assertTrue(all(a['label_seq_id'] is None and a['sequence_position'] is None for a in atoms))

    def test_duplicate_invalid_element_and_nonfinite_are_rejected(self):
        for atoms in ([glycan(), glycan()], [{**glycan(), 'element': 'Xe'}],
                      [{**glycan(), 'xyz': [float('nan'), 0, 0]}],
                      [{**glycan(), 'sequence_position': 1}]):
            with self.assertRaises(ValueError):
                a03.compare(self.protein, atoms)

    def test_fixed_protein_coordinates_and_context_preserved(self):
        context = [glycan()]
        saved = copy.deepcopy((self.protein, context))
        fingerprint = a03.fingerprints(self.protein)
        a03.compare(self.protein, context)
        self.assertEqual(saved, (self.protein, context))
        self.assertEqual(fingerprint, a03.fingerprints(self.protein))


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = [a03.baseline.load_reference(p) for p in a03.baseline.PDBS]
        cls.contexts = [a03.load_context(r) for r in cls.refs]
        cls.output = a03.HERE / 'generated'
        cls.summary = a03.baseline.read_json(cls.output / 'summary.json')
        cls.fragments = a03.baseline.read_json(cls.output / 'service-fragments.json')

    def test_assembly_specific_glycan_inventory_and_covalent_endpoints(self):
        expected = [({('D', 766), ('E', 738)}, 28, {165, 237}, 2),
                    ({('G', 1), ('G', 2), ('H', 1), ('H', 2), ('L', 1006)}, 70, {165, 237, 508}, 5)]
        for ref, (atoms, inventory), (ids, count, roots, link_count) in zip(self.refs, self.contexts, expected):
            self.assertEqual({(a['label_asym_id'], a['auth_seq_id']) for a in atoms}, ids)
            self.assertEqual(len(atoms), count)
            self.assertEqual(len(inventory['covalent_links']), link_count)
            actual_roots = {e['residue']['auth_seq_id'] for link in inventory['covalent_links']
                            for e in link['endpoints'] if e['component'] == 'ASN'}
            self.assertEqual(actual_roots, roots)
            for link in inventory['covalent_links']:
                self.assertAlmostEqual(link['observed_distance_angstrom'],
                                       float(link['annotation']['pdbx_dist_value']), delta=0.002)
            self.assertEqual(inventory['state'], 'observed_partial')
            self.assertTrue(all(a['element'] in ('C', 'N', 'O') for a in atoms))

    def test_water_ions_and_unselected_assembly_are_excluded(self):
        self.assertEqual(self.contexts[0][1]['excluded_nonprotein_atoms'], {'SO4': 5, 'HOH': 79})
        self.assertEqual(self.contexts[1][1]['excluded_nonprotein_atoms'], {})
        self.assertFalse({a['label_asym_id'] for a in self.contexts[1][0]} & {'I', 'J', 'K', 'M'})

    def test_ambiguous_occupancy_altloc_unknown_sugar_and_element_fail(self):
        ref = self.refs[0]
        cif = a03.baseline.MMCIF2Dict(str(ref.path))
        raw = a03.baseline.inputs.rows(cif, '_atom_site')
        template = next(a for a in raw if a['label_comp_id'] == 'NAG')
        components = a03.baseline.inputs.rows(cif, '_chem_comp')
        for update in ({'occupancy': '0'}, {'occupancy': '0.5'}, {'label_alt_id': 'A'},
                       {'pdbx_PDB_model_num': '2'}, {'type_symbol': 'Xe'}):
            with self.assertRaises(ValueError):
                a03.select_glycans([{**template, **update}], components)
        with self.assertRaisesRegex(ValueError, 'Unreviewed saccharide'):
            a03.select_glycans([{**template, 'label_comp_id': 'BMA'}],
                               components + [{'id': 'BMA', 'type': 'D-saccharide'}])
        atoms, _ = a03.select_glycans([{**template, 'type_symbol': 'H'}], components)
        self.assertEqual(atoms, [])

    def test_missing_or_ambiguous_covalent_endpoints_fail(self):
        ref = self.refs[1]
        raw = a03.baseline.inputs.rows(a03.baseline.MMCIF2Dict(str(ref.path)), '_atom_site')
        link = self.contexts[1][1]['covalent_links'][0]['annotation']
        endpoint = a03.link_endpoint(link, 2, raw)
        for changed in ([a for a in raw if a is not endpoint], raw + [endpoint]):
            with self.assertRaisesRegex(ValueError, 'absent or ambiguous'):
                a03.link_endpoint(link, 2, changed)
        with self.assertRaisesRegex(ValueError, 'symmetry'):
            a03.link_endpoint({**link, 'ptnr2_symmetry': '2_555'}, 2, raw)

    def test_core_matches_a02_and_per_residue_totals_at_both_resolutions(self):
        old = a03.baseline.read_json(a03.A02 / 'generated/summary.json')
        for ref, entry, old_entry in zip(self.refs, self.summary['entries'], old['entries']):
            with (self.output / f'{ref.pdb.lower()}-protein-sasa.csv').open(encoding='utf-8', newline='') as stream:
                rows = list(csv.DictReader(stream))
            expected_keys = {a.residue_key for a in ref.atoms}
            self.assertEqual(entry['core_protein_fingerprint'], entry['context_protein_fingerprint'])
            self.assertEqual(entry['core_protein_fingerprint'], a03.fingerprints(ref.atoms))
            for value, baseline_value in zip(entry['sasa'], old_entry['sasa']):
                selected = [r for r in rows if int(r['points']) == value['points']]
                self.assertEqual({(r['label_asym_id'], int(r['label_seq_id'])) for r in selected}, expected_keys)
                self.assertEqual(len(selected), len(expected_keys))
                self.assertAlmostEqual(value['core_protein_sasa'], baseline_value['complex_sasa'], places=7)
                self.assertAlmostEqual(value['reduction'], value['core_protein_sasa'] - value['context_protein_sasa'], places=7)
                for field, total in (('core', 'core_protein_sasa'), ('context', 'context_protein_sasa'), ('reduction', 'reduction')):
                    self.assertAlmostEqual(sum(float(r[f'{field}_sasa_angstrom2']) for r in selected), value[total], places=7)
                    self.assertAlmostEqual(sum(r[field] for r in value['by_role'].values()), value[total], places=7)
                self.assertTrue(all(float(r['reduction_sasa_angstrom2']) >= -1e-8 for r in selected))
            self.assertAlmostEqual(entry['reduction_resolution_difference_angstrom2'],
                                   abs(entry['sasa'][0]['reduction'] - entry['sasa'][1]['reduction']), places=7)

    def test_missing_residues_and_partial_atom_annotations_preserved(self):
        for ref, entry in zip(self.refs, self.summary['entries']):
            self.assertEqual(entry['coverage'], ref.coverage)
            self.assertEqual(entry['missing_atom_annotations'], ref.missing_atoms)
        self.assertEqual(len(self.summary['entries'][0]['missing_atom_annotations']), 12)
        self.assertEqual([r['missing_residues'] for r in self.summary['entries'][0]['coverage']], [26, 0, 0])
        self.assertEqual([r['missing_residues'] for r in self.summary['entries'][1]['coverage']], [52, 4, 0])

    def test_contract_conditions_dependency_and_unknown_states(self):
        a03.validate_fragments(self.fragments)
        self.assertEqual(len(self.fragments['conditions']), 4)
        for item in self.fragments['evidence']:
            if item['topic'] in ('atom_clash', 'whole_range_accessibility'):
                self.assertIsNone(item['value'])
                self.assertIn(item['measurement_state'], ('not_run', 'unknown'))
        bad = copy.deepcopy(self.fragments)
        bad['a02_dependency']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'dependency'):
            a03.validate_fragments(bad)
        bad = copy.deepcopy(self.fragments)
        bad['evidence'][0]['candidate_id'] = 'wrong-candidate'
        with self.assertRaisesRegex(ValueError, 'Cross-candidate'):
            a03.validate_fragments(bad)

    def test_recorded_hashes_and_original_input_preservation(self):
        report = a03.baseline.read_json(self.output / 'provenance.json')
        for item in report['inputs_and_implementation'] + report['source_files']:
            self.assertEqual(a03.baseline.digest(a03.ROOT / item['path']), item['sha256'])
        for item in report['output_files']:
            self.assertEqual(a03.baseline.digest(self.output / item['path']), item['sha256'])

    def test_reproducible_full_rebuild(self):
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stdout(io.StringIO()):
                a03.run(Path(temp))
            for p in self.output.iterdir():
                if p.suffix in ('.csv', '.json') and p.name not in ('provenance.json', 'validation.json'):
                    self.assertEqual(p.read_bytes(), (Path(temp) / p.name).read_bytes(), p.name)


if __name__ == '__main__':
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (GeometryTests, ReferenceTests)])
    names = [test.id().split('.')[-1] for group in suite for test in group]
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=2).run(suite)
    report = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests_run': result.testsRun,
              'tests': names, 'failures': [{'test': str(t), 'detail': d} for t, d in result.failures],
              'errors': [{'test': str(t), 'detail': d} for t, d in result.errors],
              'test_implementation_sha256': a03.baseline.digest(Path(__file__)),
              'basis': 'Analytic cap; original assembly/connection identity; unchanged A-02 baseline; missing data; schema; byte reproducibility'}
    a03.baseline.write_json(a03.HERE / 'generated/validation.json', report)
    print(json.dumps({'status': report['status'], 'tests_run': result.testsRun,
                      'failures': len(result.failures), 'errors': len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
