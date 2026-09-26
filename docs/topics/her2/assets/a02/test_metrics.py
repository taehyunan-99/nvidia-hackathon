import contextlib
import copy
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from Bio.PDB import NeighborSearch

import analyze
import metrics


def atom(chain, label, xyz, element="C", name="CA"):
    return metrics.Coordinate(chain, label, name, element, xyz)


class GeometryTests(unittest.TestCase):
    def test_contact_boundary_and_unique_residues(self):
        target = [atom("T", 1, (0, 0, 0)), atom("T", 1, (0, 0, 1), name="CB")]
        antibody = [atom("A", 2, (4.5, 0, 0)), atom("A", 3, (4.501, 0, 0))]
        result = metrics.interface(target, antibody)
        self.assertEqual([(i, j) for i, j, _, _ in result["pairs"]], [(0, 0)])
        self.assertEqual(result["minimum_distance"], 4.5)
        self.assertEqual(result["maximum_overlap"], 0)

    def test_empty_partner_is_unknown_not_zero(self):
        result = metrics.interface([atom("T", 1, (0, 0, 0))], [])
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["minimum_distance"])
        self.assertIsNone(result["maximum_overlap"])
        self.assertEqual(metrics.surface([], [atom("A", 1, (0, 0, 0))])["state"], "unknown")

    def test_measured_no_contact_and_known_overlap(self):
        a = [atom("T", 1, (0, 0, 0))]
        far = metrics.interface(a, [atom("A", 1, (10, 0, 0))])
        self.assertEqual((far["state"], far["pairs"]), ("measured", []))
        close = metrics.interface(a, [atom("A", 1, (3, 0, 0))])
        self.assertAlmostEqual(close["maximum_overlap"], 0.4)

    def test_unsupported_nonfinite_duplicate_atoms_are_rejected(self):
        cases = [[atom("A", 1, (0, 0, 0), "X")], [atom("A", 1, (math.nan, 0, 0))],
                 [atom("A", 1, (0, 0, 0)), atom("A", 1, (1, 0, 0))]]
        for atoms in cases:
            with self.subTest(atoms=atoms), self.assertRaises(ValueError):
                metrics.make_model(atoms)

    def test_single_and_separated_spheres_analytic_sasa(self):
        radius = 1.7 + 1.4
        expected = 4 * math.pi * radius ** 2
        single = metrics.sasa([atom("A", 1, (0, 0, 0))])
        self.assertAlmostEqual(sum(single.values()), expected, places=8)
        separated = metrics.surface([atom("T", 1, (0, 0, 0))], [atom("A", 1, (20, 0, 0))])
        self.assertAlmostEqual(separated["complex_sasa"], expected * 2, places=8)
        self.assertAlmostEqual(separated["buried_sasa_sum"], 0, places=8)

    def test_overlapping_spheres_analytic_spherical_caps(self):
        radius, distance = 3.1, 3.0
        cap_height = radius - distance / 2
        expected_buried = 4 * math.pi * radius * cap_height
        result = metrics.surface([atom("T", 1, (0, 0, 0))], [atom("A", 1, (distance, 0, 0))], 1920)
        # Discrete sphere sampling has a finite numerical integration error.
        self.assertLess(abs(result["buried_sasa_sum"] - expected_buried) / expected_buried, 0.01)
        self.assertAlmostEqual(result["target_buried_sasa"] + result["antibody_buried_sasa"],
                               result["buried_sasa_sum"], places=8)

    def test_known_rotation_translation_and_matrix_direction(self):
        fixed = np.array([[0, 0, 0], [1, 0, 0], [0, 2, 0], [0, 0, 3]], dtype=float)
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        mobile = (rotation @ fixed.T).T + [10, -3, 4]
        matrix, rmsd = metrics.fit(fixed, mobile)
        np.testing.assert_allclose(metrics.apply_matrix(mobile, matrix.ravel().tolist()), fixed, atol=1e-12)
        self.assertLess(rmsd, 1e-12)
        self.assertAlmostEqual(np.linalg.det(matrix[:3, :3]), 1)
        np.testing.assert_allclose(matrix[:3, :3], rotation.T, atol=1e-12)
        np.testing.assert_allclose(matrix[:3, 3], -rotation.T @ [10, -3, 4], atol=1e-12)

    def test_alignment_rejects_insufficient_or_degenerate_points(self):
        for points in ([[0, 0, 0], [1, 0, 0]], [[0, 0, 0], [1, 0, 0], [2, 0, 0]]):
            with self.assertRaises(ValueError):
                metrics.fit(points, points)


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = [analyze.load_reference(p) for p in analyze.PDBS]
        cls.generated = analyze.HERE / "generated"
        cls.summary = analyze.read_json(cls.generated / "summary.json")
        cls.fragments = analyze.read_json(cls.generated / "service-fragments.json")

    def test_source_hash_rejects_changed_input(self):
        with patch.object(analyze, "digest", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                analyze.load_reference("1N8Z")

    def test_mapping_corruption_rejected(self):
        original = analyze.read_json

        def corrupted(path):
            value = original(path)
            if path.name == "structures.json":
                value[0]["residue_mapping"][0]["sequence_position"] = 999
            return value

        with patch.object(analyze, "read_json", side_effect=corrupted):
            with self.assertRaisesRegex(ValueError, "mapping differs"):
                analyze.load_reference("1N8Z")

    def test_missing_ranges_and_author_insertion_codes_preserved(self):
        expected = {"1N8Z": [26, 0, 0], "1S78": [52, 4, 0]}
        for ref in self.refs:
            self.assertEqual([c["missing_residues"] for c in ref.coverage], expected[ref.pdb])
            self.assertEqual(ref.coverage[0]["selected_residues"], 607)
            for key, row in ref.selected.items():
                if not row["has_coordinates"]:
                    self.assertNotIn(key, {a.residue_key for a in ref.atoms})
        pertuzumab = self.refs[1]
        self.assertEqual(pertuzumab.coverage[0]["missing_sequence_ranges"], [[124, 132], [587, 629]])
        inserted = [pertuzumab.selected[("D", pos)] for pos in (83, 84, 85, 86)]
        self.assertEqual([r["insertion_code"] for r in inserted], [None, "A", "B", "C"])
        self.assertEqual([r["auth_seq_id"] for r in inserted], [82, 82, 82, 82])

    def test_contact_sets_match_independent_neighbor_search_and_existing_consumer(self):
        baseline = analyze.read_json(analyze.ROOT / "frontend/public/structures/contacts.json")
        expected_counts = {"1N8Z": 39, "1S78": 56}
        for ref in self.refs:
            result = metrics.interface(ref.target, ref.antibody)
            actual = {ref.target[i].residue_key for i, _, _, _ in result["pairs"]}
            actual |= {ref.antibody[j].residue_key for _, j, _, _ in result["pairs"]}
            search = NeighborSearch(list(metrics.make_model(ref.antibody).get_atoms()))
            independent = set()
            for a in ref.target:
                for b in search.search(np.array(a.xyz), 4.5):
                    independent.add(a.residue_key)
                    independent.add((b.get_parent().get_parent().id, b.get_parent().id[1]))
            self.assertEqual(actual, independent)
            self.assertEqual(actual, {(r["chain"], r["seq"]) for r in baseline[ref.pdb]["residues"]})
            self.assertEqual(len(actual), expected_counts[ref.pdb])

    def test_partial_residue_atoms_are_reported_without_fabrication(self):
        self.assertEqual([len(ref.missing_atoms) for ref in self.refs], [12, 0])
        ref = self.refs[0]
        observed = {(a.chain, a.label, a.name) for a in ref.atoms}
        self.assertEqual({(r["residue"]["label_asym_id"], r["residue"]["label_seq_id"]) for r in ref.missing_atoms},
                         {("A", 190), ("B", 30), ("B", 217)})
        self.assertEqual({r["atom_name"] for r in ref.missing_atoms}, {"CG", "CD", "CE", "NZ"})
        for row in ref.missing_atoms:
            r = row["residue"]
            self.assertTrue(r["has_coordinates"])
            self.assertNotIn((r["label_asym_id"], r["label_seq_id"], row["atom_name"]), observed)
        self.assertEqual(len(self.summary["entries"][0]["missing_atom_annotations"]), 12)

    def test_alignment_matches_correspondence_and_preserves_distances(self):
        alignment, summary = analyze.align_references(*self.refs)
        self.assertFalse(alignment["applied"])
        self.assertEqual([r["sequence_position"] for r in alignment["reference_residues"]],
                         [r["sequence_position"] for r in alignment["mobile_residues"]])
        self.assertTrue(all(r["has_coordinates"] for r in alignment["reference_residues"] + alignment["mobile_residues"]))
        fixed = {self.refs[0].selected[a.residue_key]["sequence_position"]: a for a in self.refs[0].target if a.name == "CA"}
        moving = {self.refs[1].selected[a.residue_key]["sequence_position"]: a for a in self.refs[1].target if a.name == "CA"}
        x = np.array([fixed[p].xyz for p in summary["reference_positions"]])
        y = np.array([moving[p].xyz for p in summary["reference_positions"]])
        transformed = metrics.apply_matrix(y, alignment["matrix"])
        self.assertAlmostEqual(float(np.sqrt(np.mean(np.sum((transformed - x) ** 2, axis=1)))), summary["rmsd_angstrom"])
        np.testing.assert_allclose(np.linalg.norm(np.diff(y, axis=0), axis=1),
                                   np.linalg.norm(np.diff(transformed, axis=0), axis=1), atol=1e-10)

    def test_fragments_and_no_fabricated_safety_conclusion(self):
        analyze.validate_fragments(self.fragments)
        for row in self.fragments["evidence"]:
            if row["topic"] in ("atom_clash", "whole_range_accessibility"):
                self.assertIsNone(row["value"])
                self.assertIn(row["measurement_state"], ("not_run", "unknown"))
                self.assertTrue(row["reason"])
        bad = copy.deepcopy(self.fragments)
        bad["evidence"][0]["candidate_id"] = "wrong-candidate"
        with self.assertRaisesRegex(ValueError, "Cross-candidate"):
            analyze.validate_fragments(bad)

    def test_missing_residue_cannot_be_exported_as_measured(self):
        bad = copy.deepcopy(self.fragments)
        missing = next(r for r in bad["structures"][0]["residue_mapping"] if not r["has_coordinates"])
        bad["evidence"][0]["residues"].append(missing)
        with self.assertRaisesRegex(ValueError, "Measured residue"):
            analyze.validate_fragments(bad)

    def test_surface_delta_consistency_and_finite_resolution_record(self):
        for entry in self.summary["entries"]:
            for s in entry["sasa"]:
                self.assertGreater(s["complex_sasa"], 0)
                self.assertGreaterEqual(s["buried_sasa_sum"], 0)
                self.assertAlmostEqual(s["target_buried_sasa"] + s["antibody_buried_sasa"], s["buried_sasa_sum"], places=7)
            for d in entry["sasa_resolution_difference"].values():
                self.assertTrue(math.isfinite(d["absolute_angstrom2"]))

    def test_reproducible_rebuild_and_input_preservation(self):
        locked = analyze.read_json(analyze.A01 / "source-lock.json")["sources"]
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stdout(io.StringIO()):
                analyze.run(Path(temp))
            for p in self.generated.iterdir():
                if p.suffix in (".csv", ".json") and p.name not in ("validation.json", "provenance.json"):
                    self.assertEqual(p.read_bytes(), (Path(temp) / p.name).read_bytes(), p.name)
        for source in locked:
            self.assertEqual(analyze.digest(analyze.ROOT / source["path"]), source["sha256"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GeometryTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceTests))
    names = [test.id().split(".")[-1] for test in suite]
    capture = io.StringIO()
    result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
    report = {"status": "PASS" if result.wasSuccessful() else "FAIL", "tests_run": result.testsRun,
              "tests": names, "failures": [{"test": str(t), "detail": d} for t, d in result.failures],
              "errors": [{"test": str(t), "detail": d} for t, d in result.errors],
              "basis": "Analytic geometry, original mapping, independent neighbor search, consumer set and schema checks, offline rebuild"}
    analyze.write_json(analyze.HERE / "generated/validation.json", report)
    print(json.dumps({"status": report["status"], "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
