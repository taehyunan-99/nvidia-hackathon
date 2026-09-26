from dataclasses import dataclass

import numpy as np
from Bio.PDB.Atom import Atom
from Bio.PDB.Chain import Chain
from Bio.PDB.Model import Model
from Bio.PDB.Residue import Residue
from Bio.PDB.SASA import ShrakeRupley
from Bio.SVDSuperimposer import SVDSuperimposer

RADII = {"C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80}
CONTACT_CUTOFF = 4.5
PROBE_RADIUS = 1.4


@dataclass(frozen=True)
class Coordinate:
    chain: str
    label: int
    name: str
    element: str
    xyz: tuple[float, float, float]

    @property
    def residue_key(self):
        return self.chain, self.label


def validate_atoms(atoms):
    identities = set()
    for atom in atoms:
        if atom.element not in RADII:
            raise ValueError(f"Unsupported element: {atom.element}")
        if len(atom.xyz) != 3 or not np.isfinite(atom.xyz).all():
            raise ValueError("Nonfinite or invalid coordinates")
        identity = (atom.chain, atom.label, atom.name)
        if identity in identities:
            raise ValueError(f"Duplicate atom: {identity}")
        identities.add(identity)


def interface(target, antibody, cutoff=CONTACT_CUTOFF):
    validate_atoms(target + antibody)
    if not np.isfinite(cutoff) or cutoff <= 0:
        raise ValueError("Invalid distance cutoff")
    if not target or not antibody:
        return {"state": "unknown", "reason": "A partner has no usable coordinates", "pairs": [],
                "minimum_distance": None, "maximum_overlap": None}
    xyz = np.array([a.xyz for a in antibody])
    radii = np.array([RADII[a.element] for a in antibody])
    pairs = []
    minimum = float("inf")
    maximum_overlap = 0.0
    for start in range(0, len(target), 64):
        chunk = target[start:start + 64]
        delta = np.array([a.xyz for a in chunk])[:, None, :] - xyz[None, :, :]
        distances = np.sqrt(np.sum(delta * delta, axis=2))
        overlaps = np.array([RADII[a.element] for a in chunk])[:, None] + radii - distances
        minimum = min(minimum, float(distances.min()))
        maximum_overlap = max(maximum_overlap, float(overlaps.max()))
        for i, j in zip(*np.nonzero(distances <= cutoff)):
            pairs.append((start + int(i), int(j), float(distances[i, j]), float(overlaps[i, j])))
    return {"state": "measured", "reason": None, "pairs": pairs,
            "minimum_distance": minimum, "maximum_overlap": maximum_overlap}


def make_model(atoms):
    validate_atoms(atoms)
    model = Model(0)
    for serial, item in enumerate(atoms, 1):
        if item.chain not in model:
            model.add(Chain(item.chain))
        chain = model[item.chain]
        key = (" ", item.label, " ")
        if key not in chain:
            chain.add(Residue(key, "UNK", " "))
        chain[key].add(Atom(item.name, np.array(item.xyz, dtype=float), 0, 1, " ",
                            item.name, serial, element=item.element))
    return model


def sasa(atoms, points=960):
    if not atoms:
        return None
    model = make_model(atoms)
    ShrakeRupley(probe_radius=PROBE_RADIUS, n_points=points, radii_dict=RADII).compute(model, level="R")
    return {(r.get_parent().id, r.id[1]): float(r.sasa) for r in model.get_residues()}


def surface(target, antibody, points=960):
    if not target or not antibody:
        return {"state": "unknown", "reason": "A partner has no usable coordinates"}
    complex_areas = sasa(target + antibody, points)
    target_areas = sasa(target, points)
    antibody_areas = sasa(antibody, points)
    target_total = sum(target_areas.values())
    antibody_total = sum(antibody_areas.values())
    complex_total = sum(complex_areas.values())
    return {"state": "measured", "points": points, "complex_sasa": complex_total,
            "target_isolated_sasa": target_total, "antibody_isolated_sasa": antibody_total,
            "target_buried_sasa": target_total - sum(complex_areas[k] for k in target_areas),
            "antibody_buried_sasa": antibody_total - sum(complex_areas[k] for k in antibody_areas),
            "buried_sasa_sum": target_total + antibody_total - complex_total,
            "complex_residues": complex_areas, "isolated_residues": target_areas | antibody_areas}


def fit(reference, mobile):
    reference = np.asarray(reference, dtype=float)
    mobile = np.asarray(mobile, dtype=float)
    if reference.shape != mobile.shape or reference.ndim != 2 or reference.shape[1] != 3:
        raise ValueError("Alignment requires matched Nx3 coordinates")
    if len(reference) < 3 or not np.isfinite(reference).all() or not np.isfinite(mobile).all():
        raise ValueError("Insufficient or nonfinite alignment coordinates")
    if any(np.linalg.matrix_rank(x - x.mean(axis=0)) < 2 for x in (reference, mobile)):
        raise ValueError("Degenerate alignment coordinates")
    aligner = SVDSuperimposer()
    aligner.set(reference, mobile)
    aligner.run()
    rotation, translation = aligner.get_rotran()
    matrix = np.eye(4)
    matrix[:3, :3] = rotation.T
    matrix[:3, 3] = translation
    return matrix, float(aligner.get_rms())


def apply_matrix(coords, matrix):
    coords = np.asarray(coords, dtype=float)
    matrix = np.asarray(matrix, dtype=float).reshape(4, 4)
    homogeneous = np.column_stack((coords, np.ones(len(coords))))
    return (matrix @ homogeneous.T).T[:, :3]
