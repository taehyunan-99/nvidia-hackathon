"""RCSB에서 평가셋 후보 엔트리의 폴리머 서열과 역할을 받아 온다."""
import json
import urllib.request

IDS = ["3BE1", "3WSQ", "5O4G", "6ATT", "6BGT", "9L1S", "9T3R", "9T3S", "4P59", "8YRY"]


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


out = {}
for pid in IDS:
    entry = get(f"https://data.rcsb.org/rest/v1/core/entry/{pid}")
    ids = entry["rcsb_entry_container_identifiers"]["polymer_entity_ids"]
    ents = []
    for eid in ids:
        e = get(f"https://data.rcsb.org/rest/v1/core/polymer_entity/{pid}/{eid}")
        desc = e.get("rcsb_polymer_entity", {}).get("pdbx_description", "")
        seq = e.get("entity_poly", {}).get("pdbx_seq_one_letter_code_can", "").replace("\n", "")
        names = [n.get("name", "") for n in e.get("rcsb_polymer_entity", {}).get("rcsb_macromolecular_names_combined", [])]
        ents.append({"entity_id": eid, "description": desc, "names": names, "length": len(seq), "sequence": seq})
    out[pid] = {"title": entry.get("struct", {}).get("title", ""), "entities": ents}
    print(pid, len(ents), "entities")

with open("eval_seqs.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("saved")
