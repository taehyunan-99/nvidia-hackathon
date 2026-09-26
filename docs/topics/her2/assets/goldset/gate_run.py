"""실제 PDB 10건을 후보로 넣고 도구·관문을 끝까지 구동한다.

모델을 부르지 않는다(RuleDecider). Boltz-2도 부르지 않는다(예측 응답 스텁).
확인하려는 것: 실제 항체 서열에서 입력 검사·조회·관문·보고가 끝까지 도는가.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATED = HERE / "generated"


def _repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists() and (p / "logic").is_dir():
            return p
    raise SystemExit("저장소 뿌리를 찾지 못했다(pyproject.toml + logic/).")


ROOT = _repo_root(HERE)
GOLD = str(GENERATED)
CIF = str(HERE / "cif")
sys.path.insert(0, str(ROOT))

from logic.agent import RuleDecider  # noqa: E402
from logic.agent_session import CandidateSession, CandidateTools, allowed_tools  # noqa: E402
from logic.contract import validate  # noqa: E402
from logic.flow import Flow  # noqa: E402
from logic.tests.test_flow import TRASTUZUMAB, candidate, entity_sequence, make_request  # noqa: E402
from logic.tests.test_flow_decisions import _filler  # noqa: E402

ROLE = {
    "3BE1": (2, 3, 1), "3WSQ": (3, 2, 1), "5O4G": (3, 2, 1), "6ATT": (2, 3, 1),
    "6BGT": (3, 2, 1), "9L1S": (3, 2, 1), "9T3R": (2, 1, 3), "9T3S": (1, 2, 3),
    "4P59": (2, 3, 1), "8YRY": (2, 3, 1),
}
TARGET_KIND = {"4P59": "HER3", "8YRY": "HER3"}
TARGET = entity_sequence(TRASTUZUMAB, "target")

# Boltz-2 자리에 놓는 스텁. 실제 호출을 하지 않는다.
CIF_STUB = "data_stub\n#\n"


class StubClient:
    def __init__(self):
        self.predictions = 0

    def predict_complex(self, polymers, **kw):
        self.predictions += 1
        return {"structures": [{"structure": CIF_STUB}], "confidence_scores": [0.5]}

    def chat(self, *a, **kw):
        raise AssertionError("모델을 부르면 안 된다")


seqs = json.load(open(f"{GOLD}/pdb-sequences.json"))
rows = []
print(f"{'PDB':6} {'표적':5} {'예측':4} {'상태':10} {'판정':18} {'밟은 도구'}")
for pid, v in seqs.items():
    h_id, l_id, _ = ROLE[pid]
    ents = {int(e["entity_id"]): e for e in v["entities"]}
    cand = candidate(f"cand-{pid}", pid, f">h\n{ents[h_id]['sequence']}", f">l\n{ents[l_id]['sequence']}")
    with tempfile.TemporaryDirectory() as tmp:
        req = make_request([cand, _filler()], Path(tmp), target_fasta=TARGET)
        client = StubClient()
        flow = Flow(req, client=client)
        flow.decider = RuleDecider("실측 대신 규칙", decisions=[], model=None)
        s = CandidateSession(cand)
        tools = CandidateTools(flow, s)
        trace = []
        for _ in range(8):
            allowed = allowed_tools(s)
            if not allowed:
                break
            # 관문은 완전 일치가 없으면 hold_candidate와 predict_structure를 함께 연다.
            # 정답은 서열이 충분히 길면 예측이다(hold는 "서열이 없거나 너무 짧을 때만").
            for prefer in ("use_experimental_structure", "predict_structure"):
                if prefer in allowed:
                    name = prefer
                    break
            else:
                name = sorted(allowed)[0]
            fn = getattr(tools, name)
            out = fn("실제 구조 대조용 구동") if name in (
                "use_experimental_structure", "predict_structure", "hold_candidate") else (
                fn("needs_confirmation", "미계산 항목이 있어 확인이 필요하다.")
                if name == "submit_opinion" else fn())
            trace.append(name + ("" if not str(out).startswith("거부") else "✗"))
        op = next((o for o in flow.opinions if o["candidate_id"] == cand["candidate_id"]), None)
        dec = op["decision"] if op else "-"
        st = flow.states[cand["candidate_id"]].status
        rows.append({"pdb": pid, "target": TARGET_KIND.get(pid, "HER2"), "status": st,
                     "decision": dec, "predictions": client.predictions, "trace": trace})
        print(f"{pid:6} {TARGET_KIND.get(pid,'HER2'):5} {client.predictions:<4} {st:10} {dec:18} "
              f"{' → '.join(trace)}")

json.dump(rows, open(f"{GOLD}/gate-run.json", "w"), ensure_ascii=False, indent=1)
print()
print("끝까지 간 건수:", sum(1 for r in rows if r["status"] == "completed"), "/", len(rows))
print("거부 발생 건수:", sum(1 for r in rows if any("✗" in t for t in r["trace"])))
