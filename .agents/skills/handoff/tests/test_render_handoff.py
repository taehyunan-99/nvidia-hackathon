from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = SKILL_ROOT / "scripts" / "render_handoff.py"
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_handoff.py"

_SPEC = importlib.util.spec_from_file_location(
    "handoff_render_contract",
    RENDERER_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load renderer: {RENDERER_PATH}")
RENDERER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(RENDERER)



def valid_handoff() -> str:
    return textwrap.dedent(
        """\
        # HANDOFF

        Format: handoff-v2
        Receipt: READY
        Work status: ACTIVE
        Project scope: .
        Last verified: 2026-07-29T17:00:00+09:00
        Baseline commit: abc1234
        Branch or worktree: main
        First action: Inspect scripts/render_handoff.py and finish C1.

        ## Resume instructions

        1. Verify the baseline and working tree.
        2. Start the first unfinished stage.

        ## Strategic alignment

        - Objective: preserve verified work across sessions.
        - Guardrail: do not create control-plane state.

        ## Documentation alignment

        | Topic or decision | Authority | Alignment | Action | Evidence |
        | --- | --- | --- | --- | --- |
        | Handoff direction | docs/ARCHITECTURE.md#handoff | ALIGNED | No update required | E1 |

        ## Global success criteria

        | ID | Criterion | Required | Status | Evidence |
        | --- | --- | --- | --- | --- |
        | C1 | The renderer contract is verified | yes | UNVERIFIED | E2 |
        | C2 | Durable documentation is aligned | yes | PASS | E1 |

        ## Plan review

        | Change | Previous | Revised | Reason | Documentation impact |
        | --- | --- | --- | --- | --- |
        | Keep one stage | Two overlapping stages | One bounded stage | Smaller verified plan | No durable documentation change |

        ## Execution plan

        ### S1 — Verify renderer

        State: ACTIVE
        Maps to: C1
        Outcome: Renderer behavior has direct evidence.
        Scope: scripts/render_handoff.py and tests/test_render_handoff.py
        Verification: Run the focused unittest file.
        First action: Inspect scripts/render_handoff.py and finish C1.

        | Gate or criterion | Status | Evidence |
        | --- | --- | --- |
        | deliverable | UNVERIFIED | E2 |
        | scope | UNVERIFIED | E2 |
        | documentation | PASS | E1 |
        | verification | UNVERIFIED | E2 |
        | evidence | UNVERIFIED | E2 |
        | next-input | UNVERIFIED | E2 |
        | S1-contract-tests | UNVERIFIED | E2 |

        ## Evidence

        | ID | Kind | Result | Summary | Reference |
        | --- | --- | --- | --- | --- |
        | E1 | document | PASS | Architecture direction was read directly. | docs/ARCHITECTURE.md#handoff |
        | E2 | test | UNVERIFIED | Focused tests still need to run. | tests/test_render_handoff.py |

        ## State verification

        - Branch: main
        - HEAD: abc1234
        - Working tree: test changes only
        - Evidence: E1

        ## Risks and open questions

        - Focused tests have not run yet.

        ## Required context

        1. `docs/ARCHITECTURE.md`
        2. `scripts/render_handoff.py`
        3. `tests/test_render_handoff.py`

        ### Next-stage routing

        - Goal: Renderer behavior has direct evidence.
        - Completion condition: Focused unittest passes and all S1 gates are PASS.
        - Current stage: S1 — Verify renderer
        - Change scope: scripts/render_handoff.py and tests/test_render_handoff.py
        - Recommended model: Terra
        - Recommended reasoning: High
        - Use Ultra: no
        - Escalate to Sol High when: Parser or output safety boundaries become ambiguous.
        - Next checkpoint: After the focused unittest result is available.

        ## New-session prompt

        ```text
        $handoff
        Handoff action: RESUME
        Project scope: .
        Receipt: docs/HANDOFF.md
        Expected baseline: abc1234
        First action: Inspect scripts/render_handoff.py and finish C1.
        Goal: Renderer behavior has direct evidence.
        Completion condition: Focused unittest passes and all S1 gates are PASS.
        Current stage: S1 — Verify renderer
        Change scope: scripts/render_handoff.py and tests/test_render_handoff.py
        Recommended model: Terra
        Recommended reasoning: High
        Use Ultra: no
        Escalate to Sol High when: Parser or output safety boundaries become ambiguous.
        Next checkpoint: After the focused unittest result is available.
        Routing is advisory: revalidate repository state and adjust model, reasoning, or Ultra if evidence changed.
        Begin actual work.
        Do not create a new handoff, report, or prompt.
        ```
        """
    )


def legacy_handoff() -> str:
    text = valid_handoff()
    context = section_body(text, "Required context", "New-session prompt")
    context = context.split(RENDERER.ROUTING_HEADING, 1)[0].rstrip()
    text = replace_section_body(
        text,
        "Required context",
        "New-session prompt",
        context,
    )
    prompt = terminal_section_body(text, "New-session prompt")
    routing_prefixes = tuple(f"{key}:" for key in RENDERER.ROUTING_FIELDS)
    legacy_prompt = "\n".join(
        line
        for line in prompt.splitlines()
        if not line.strip().startswith(routing_prefixes)
        and line.strip() != RENDERER.ROUTING_ADVISORY
    )
    return replace_terminal_section_body(
        text,
        "New-session prompt",
        legacy_prompt,
    )


def completed_handoff() -> str:
    text = legacy_handoff()
    replacements = {
        "Work status: ACTIVE": "Work status: COMPLETE",
        "| C1 | The renderer contract is verified | yes | UNVERIFIED | E2 |": (
            "| C1 | The renderer contract is verified | yes | PASS | E2 |"
        ),
        (
            "| E2 | test | UNVERIFIED | Focused tests still need to run. | "
            "tests/test_render_handoff.py |"
        ): (
            "| E2 | test | PASS | Focused tests passed. | "
            "tests/test_render_handoff.py |"
        ),
    }
    for old, new in replacements.items():
        text = replace_once(text, old, new)
    text = replace_section_body(
        text,
        "Execution plan",
        "Evidence",
        "No remaining stages.",
    )
    text = replace_terminal_section_body(
        text,
        "New-session prompt",
        "No new-session prompt: work is complete.",
    )
    return text


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(
            f"fixture replacement expected one occurrence of {old!r}, "
            f"found {text.count(old)}"
        )
    return text.replace(old, new, 1)


def section_body(text: str, section: str, next_section: str) -> str:
    start_token = f"## {section}\n"
    end_token = f"## {next_section}\n"
    start = text.index(start_token) + len(start_token)
    end = text.index(end_token, start)
    return text[start:end].strip()


def replace_section_body(
    text: str,
    section: str,
    next_section: str,
    body: str,
) -> str:
    start_token = f"## {section}\n"
    end_token = f"## {next_section}\n"
    start = text.index(start_token) + len(start_token)
    end = text.index(end_token, start)
    return text[:start] + f"\n{body.strip()}\n\n" + text[end:]


def replace_terminal_section_body(text: str, section: str, body: str) -> str:
    start_token = f"## {section}\n"
    start = text.index(start_token) + len(start_token)
    return text[:start] + f"\n{body.strip()}\n"


def terminal_section_body(text: str, section: str) -> str:
    start_token = f"## {section}\n"
    start = text.index(start_token) + len(start_token)
    return text[start:].strip()


def current_pause_handoff() -> str:
    text = valid_handoff().replace("Format: handoff-v2", "Format: handoff-v3", 1)
    state = "\n".join(
        (
            "- Branch or worktree: main",
            "- HEAD: abc1234",
            "- Working tree: test changes only",
            "- Evidence: E1",
            "",
            "### Handoff completion checklist",
            "",
            "- repository-snapshot: PASS; E1",
            "- work-state: PASS; E1",
            "- documentation: PASS; E1",
            "- evidence: PASS; E1",
            "- resume-ready: PASS; E1",
        )
    )
    text = replace_section_body(
        text,
        "State verification",
        "Risks and open questions",
        state,
    )
    context = section_body(text, "Required context", "New-session prompt")
    context = context.replace(
        "### Next-stage routing",
        "\n".join(
            (
                "### Continuation decision",
                "",
                "- Mode: PAUSE",
                "- Branch or worktree: main",
                "- Instruction: Resume the recorded current stage.",
                "",
                "### Next-stage routing",
            )
        ),
        1,
    )
    text = replace_section_body(
        text,
        "Required context",
        "New-session prompt",
        context,
    )
    prompt = "\n".join(
        (
            "```text",
            "$handoff start",
            "Project scope: .",
            "Receipt: docs/HANDOFF.md",
            "Expected baseline: abc1234",
            "Branch or worktree: main",
            "Selected route: PAUSE",
            "First action: Inspect scripts/render_handoff.py and finish C1.",
            "Goal: Renderer behavior has direct evidence.",
            "Completion condition: Focused unittest passes and all S1 gates are PASS.",
            "Current stage: S1 \u2014 Verify renderer",
            "Change scope: scripts/render_handoff.py and tests/test_render_handoff.py",
            "Begin actual work.",
            "Do not create a new handoff, report, or prompt.",
            "```",
        )
    )
    return replace_terminal_section_body(text, "New-session prompt", prompt)

def current_v5_handoff() -> str:
    text = current_pause_handoff().replace(
        "Format: handoff-v3",
        "Format: handoff-v5",
        1,
    )
    text = replace_once(
        text,
        "### Continuation decision\n\n"
        "- Mode: PAUSE\n"
        "- Branch or worktree: main\n"
        "- Instruction: Resume the recorded current stage.\n\n",
        "",
    )
    text = replace_section_body(
        text,
        "Resume instructions",
        "Strategic alignment",
        "\n".join(
            (
                "1. Verify the baseline and working tree.",
                "2. Start the first unfinished stage.",
                "",
                "### 작업 결과 요약",
                "",
                "- 한 줄 결과: 검색 결과 검증 작업을 완료했습니다.",
                "- 바뀐 점: 다음 세션에서 검증된 상태를 바로 이어갈 수 있습니다.",
                "- 이제 가능한 것: 다음 개발 작업을 시작할 수 있습니다.",
                "- 확인한 내용: 현재 상태와 검증 기록을 확인했습니다.",
                "- 남은 사항: 다음 작업의 구현을 진행합니다.",
            )
        ),
    )
    return replace_terminal_section_body(
        text,
        "New-session prompt",
        "No copyable prompt: start reads this receipt directly.",
    )


def current_v6_handoff() -> str:
    text = current_v5_handoff().replace(
        "Format: handoff-v5",
        "Format: handoff-v6",
        1,
    )
    text = replace_once(
        text,
        "- Recommended model: Terra\n"
        "- Recommended reasoning: High\n",
        "- Recommended model: Luna\n"
        "- Recommended reasoning: High\n"
        "- Route availability: active\n"
        "- Fallback model: not-applicable\n"
        "- Fallback reasoning: not-applicable\n",
    )
    return text


def current_v7_handoff() -> str:
    text = current_v6_handoff().replace("handoff-v6", "handoff-v7")
    for line in (
        "- Route availability: active\n",
        "- Fallback model: not-applicable\n",
        "- Fallback reasoning: not-applicable\n",
    ):
        text = text.replace(line, "")
    return text.replace("Escalate to Sol High when", "Escalate when")


class RenderHandoffContractTests(unittest.TestCase):
    def make_project(self, source: str | None = None) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "project"
        docs = root / "docs"
        docs.mkdir(parents=True)
        (docs / "HANDOFF.md").write_text(
            source if source is not None else valid_handoff(),
            encoding="utf-8",
            newline="\n",
        )
        return root

    def run_renderer(
        self,
        root: Path,
        *,
        handoff: str | None = None,
        output: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(RENDERER_PATH),
            "--project-root",
            str(root),
        ]
        if handoff is not None:
            command.extend(["--handoff", handoff])
        if output is not None:
            command.extend(["--output", output])
        return subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--project-root",
                str(root),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def assert_invalid(self, source: str, message: str | None = None) -> None:
        with self.assertRaises(RENDERER.HandoffError) as caught:
            RENDERER.parse_handoff(source)
        if message is not None:
            self.assertIn(message, str(caught.exception))

    def test_valid_receipt_renders_deterministically(self) -> None:
        root = self.make_project()
        source = root / "docs" / "HANDOFF.md"
        output = root / "docs" / "HANDOFF.html"

        first = self.run_renderer(root)
        self.assertEqual(first.returncode, 0, first.stderr)
        first_bytes = output.read_bytes()

        second = self.run_renderer(root)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(output.read_bytes(), first_bytes)
        self.assertIn(str(output), second.stdout)
        self.assertTrue(
            first_bytes.startswith(
                (
                    "<!-- Generated by Handoff renderer; source-sha256="
                    + hashlib.sha256(source.read_bytes()).hexdigest()
                ).encode("ascii")
            )
        )
        self.assertFalse(
            (root / "docs" / "HANDOFF.html.handoff-render.lock").exists()
        )

    def test_user_content_is_escaped_and_page_has_strict_csp_without_js(
        self,
    ) -> None:
        payload = '<script>alert("x")</script> & "quoted"'
        source = replace_once(
            valid_handoff(),
            "preserve verified work across sessions.",
            payload,
        )
        root = self.make_project(source)

        result = self.run_renderer(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = (root / "docs" / "HANDOFF.html").read_text(encoding="utf-8")
        compact = rendered.lower()

        self.assertIn(
            "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; "
            "&amp; &quot;quoted&quot;",
            rendered,
        )
        self.assertNotIn("<script", compact)
        self.assertNotIn("javascript:", compact)
        self.assertNotIn("window.", compact)
        self.assertNotIn("https://", compact)
        self.assertIn(
            "default-src 'none'; style-src 'unsafe-inline'; font-src data:;",
            rendered,
        )


    def test_routing_packet_is_parsed_and_rendered_as_advisory(self) -> None:
        model = RENDERER.parse_handoff(valid_handoff())

        self.assertEqual(
            model["routing"],
            {
                "Goal": "Renderer behavior has direct evidence.",
                "Completion condition": (
                    "Focused unittest passes and all S1 gates are PASS."
                ),
                "Current stage": "S1 — Verify renderer",
                "Change scope": (
                    "scripts/render_handoff.py and tests/test_render_handoff.py"
                ),
                "Recommended model": "Terra",
                "Recommended reasoning": "High",
                "Use Ultra": "no",
                "Escalate to Sol High when": (
                    "Parser or output safety boundaries become ambiguous."
                ),
                "Next checkpoint": (
                    "After the focused unittest result is available."
                ),
            },
        )
        rendered = RENDERER.render_html(model, "0" * 64)
        self.assertIn("<h1>Renderer behavior has direct evidence.</h1>", rendered)
        self.assertIn("새 세션 설정", rendered)
        route_start = rendered.index("<section class='section route-section'>")
        route_end = rendered.index("</section>", route_start) + len("</section>")
        routing_card = rendered[route_start:route_end]
        self.assertIn("Terra", routing_card)
        self.assertIn("High", routing_card)
        self.assertIn("<span>Ultra</span><strong>no</strong>", routing_card)
        self.assertIn("상위 라우팅 전환 조건", routing_card)
        self.assertIn(
            "Parser or output safety boundaries become ambiguous.",
            routing_card,
        )
        self.assertIn(
            "After the focused unittest result is available.",
            routing_card,
        )
        self.assertIn("content:\"+\"", rendered)
        self.assertIn("모델 추천은 복사 프롬프트와 별개입니다", rendered)
        self.assertIn("role=progressbar", rendered)
        self.assertIn("aria-current=step", rendered)

    def test_legacy_v2_without_routing_still_parses_and_renders(self) -> None:
        source = replace_once(
            legacy_handoff(),
            "3. `tests/test_render_handoff.py`",
            "3. `tests/test_render_handoff.py`\n- Goal: legacy free-form context",
        )
        prompt = replace_once(
            terminal_section_body(source, "New-session prompt"),
            "First action: Inspect scripts/render_handoff.py and finish C1.\n",
            "First action: Inspect scripts/render_handoff.py and finish C1.\nGoal: legacy prompt context\n",
        )
        source = replace_terminal_section_body(
            source,
            "New-session prompt",
            prompt,
        )
        model = RENDERER.parse_handoff(source)
        self.assertIsNone(model["routing"])

        rendered = RENDERER.render_html(model, "1" * 64)
        self.assertIn("Legacy handoff-v2 receipt", rendered)
        self.assertIn("RESUME에서 저장소 상태와 단계 복잡도를 다시 평가", rendered)
        self.assertIn("기존 v2 영수증에 별도 확인 시점이 기록되지 않았습니다.", rendered)

    def test_legacy_unpunctuated_goal_has_a_safe_heading(self) -> None:
        source = replace_section_body(
            legacy_handoff(),
            "Strategic alignment",
            "Documentation alignment",
            "A short goal without terminal punctuation",
        )
        rendered = RENDERER.render_html(
            RENDERER.parse_handoff(source),
            "3" * 64,
        )
        self.assertIn("<h1>A short goal without terminal punctuation</h1>", rendered)

    def test_complete_report_does_not_encourage_resume(self) -> None:
        rendered = RENDERER.render_html(
            RENDERER.parse_handoff(completed_handoff()),
            "4" * 64,
        )
        self.assertIn("<h2>작업이 완료되었습니다</h2>", rendered)
        self.assertNotIn("Legacy handoff-v2 receipt", rendered)
        self.assertNotIn("<h2>모델 라우팅</h2>", rendered)
        self.assertNotIn("<h2>재개 프롬프트</h2>", rendered)
        self.assertNotIn("Run first", rendered)
        self.assertNotIn("다음에 할 일</h2>", rendered)

    def test_rendered_html_has_semantic_structure_and_inline_code(self) -> None:
        from html.parser import HTMLParser

        source = replace_once(
            valid_handoff(),
            (
                "| Handoff direction | docs/ARCHITECTURE.md#handoff | "
                "ALIGNED | No update required | E1 |"
            ),
            (
                "| Handoff direction | `docs/ARCHITECTURE.md#handoff` | "
                "ALIGNED | No update required | E1 |"
            ),
        )
        rendered = RENDERER.render_html(
            RENDERER.parse_handoff(source),
            "5" * 64,
        )

        class SemanticParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.starts: list[tuple[str, dict[str, str | None]]] = []

            def handle_starttag(
                self,
                tag: str,
                attrs: list[tuple[str, str | None]],
            ) -> None:
                self.starts.append((tag, dict(attrs)))

        parser = SemanticParser()
        parser.feed(rendered)
        parser.close()
        tags = [tag for tag, _ in parser.starts]
        self.assertEqual(tags.count("main"), 1)
        self.assertEqual(tags.count("h1"), 1)
        self.assertGreaterEqual(tags.count("details"), 2)
        self.assertTrue(
            any(attrs.get("role") == "progressbar" for _, attrs in parser.starts)
        )
        self.assertIn("<code>docs/ARCHITECTURE.md#handoff</code>", rendered)


    def test_partial_duplicate_or_mismatched_routing_is_rejected(self) -> None:
        partial = replace_once(
            valid_handoff(),
            "- Next checkpoint: After the focused unittest result is available.\n",
            "",
        )
        self.assert_invalid(partial, "missing next-stage routing fields")

        duplicate = replace_once(
            valid_handoff(),
            "- Use Ultra: no\n",
            "- Use Ultra: no\n- Use Ultra: no\n",
        )
        self.assert_invalid(duplicate, "duplicate next-stage routing field")

        prompt = replace_once(
            terminal_section_body(valid_handoff(), "New-session prompt"),
            "Recommended model: Terra",
            "Recommended model: Sol",
        )
        mismatch = replace_terminal_section_body(
            valid_handoff(),
            "New-session prompt",
            prompt,
        )
        self.assert_invalid(mismatch, "does not match Required context")

    def test_routing_matrix_has_medium_floor_and_extra_high_ceiling(self) -> None:
        accepted_routes = {
            ("Terra", "Medium"),
            ("Terra", "High"),
            ("Sol", "Medium"),
            ("Sol", "High"),
            ("Sol", "Extra High"),
        }
        self.assertEqual(RENDERER.LEGACY_ROUTING_COMBINATIONS, accepted_routes)

        for model_name, reasoning in sorted(accepted_routes):
            with self.subTest(accepted=(model_name, reasoning)):
                source = valid_handoff().replace(
                    "Recommended model: Terra",
                    f"Recommended model: {model_name}",
                ).replace(
                    "Recommended reasoning: High",
                    f"Recommended reasoning: {reasoning}",
                )
                if (model_name, reasoning) == ("Sol", "Extra High"):
                    source = source.replace(
                        "Parser or output safety boundaries become ambiguous.",
                        (
                            "Already at Sol + Extra High; retain it while "
                            "architecture boundaries remain unresolved; evidence E1."
                        ),
                    ).replace(
                        "Architecture direction was read directly.",
                        "Top-route evidence: architecture boundaries are unresolved.",
                    )
                parsed = RENDERER.parse_handoff(source)
                self.assertEqual(parsed["routing"]["Recommended model"], model_name)
                self.assertEqual(
                    parsed["routing"]["Recommended reasoning"],
                    reasoning,
                )
                rendered = RENDERER.render_html(parsed, "6" * 64)
                route_start = rendered.index(
                    "<section class='section route-section'>"
                )
                route_end = rendered.index("</section>", route_start)
                routing_card = rendered[route_start:route_end]
                self.assertIn(f"<strong>{model_name}</strong>", routing_card)
                self.assertIn(f"<strong>{reasoning}</strong>", routing_card)

        top_route_without_evidence = valid_handoff().replace(
            "Recommended model: Terra",
            "Recommended model: Sol",
        ).replace(
            "Recommended reasoning: High",
            "Recommended reasoning: Extra High",
        )
        self.assert_invalid(
            top_route_without_evidence,
            "must record highest-route evidence",
        )
        top_route_without_detail = top_route_without_evidence.replace(
            "Parser or output safety boundaries become ambiguous.",
            RENDERER.TOP_ROUTE_ESCALATION_PREFIX,
        )
        self.assert_invalid(
            top_route_without_detail,
            "must record highest-route evidence",
        )

        top_route_with_non_pass_evidence = top_route_without_evidence.replace(
            "Parser or output safety boundaries become ambiguous.",
            (
                "Already at Sol + Extra High; retain it while architecture "
                "boundaries remain unresolved; evidence E2."
            ),
        )
        self.assert_invalid(
            top_route_with_non_pass_evidence,
            "references non-PASS evidence",
        )

        top_route_without_summary = top_route_without_evidence.replace(
            "Parser or output safety boundaries become ambiguous.",
            (
                "Already at Sol + Extra High; retain it while architecture "
                "boundaries remain unresolved; evidence E1."
            ),
        )
        self.assert_invalid(
            top_route_without_summary,
            "requires a 'Top-route evidence:' PASS summary",
        )

        legacy_routes = (
            ("Luna", "Light"),
            ("Terra", "Light"),
        )
        for model_name, reasoning in legacy_routes:
            with self.subTest(legacy=(model_name, reasoning)):
                source = valid_handoff().replace(
                    "Recommended model: Terra",
                    f"Recommended model: {model_name}",
                ).replace(
                    "Recommended reasoning: High",
                    f"Recommended reasoning: {reasoning}",
                )
                self.assert_invalid(source, "requires in-place migration")

        rejected_routes = (
            ("Sol", "Light"),
            ("Luna", "Medium"),
            ("Terra", "Extra High"),
            ("Sol", "xhigh"),
        )
        for model_name, reasoning in rejected_routes:
            with self.subTest(rejected=(model_name, reasoning)):
                source = valid_handoff().replace(
                    "Recommended model: Terra",
                    f"Recommended model: {model_name}",
                ).replace(
                    "Recommended reasoning: High",
                    f"Recommended reasoning: {reasoning}",
                )
                self.assert_invalid(
                    source,
                    "unsupported model/reasoning combination",
                )

    def test_handoff_v7_routes_without_availability_or_fallbacks(self) -> None:
        for model_name, reasoning in RENDERER.ROUTING_COMBINATIONS:
            with self.subTest(route=(model_name, reasoning)):
                source = current_v7_handoff().replace(
                    "- Recommended model: Luna", f"- Recommended model: {model_name}"
                ).replace(
                    "- Recommended reasoning: High", f"- Recommended reasoning: {reasoning}"
                )
                parsed = RENDERER.parse_handoff(source)
                rendered = RENDERER.render_html(parsed, "a" * 64)
                self.assertEqual(parsed["metadata"]["Format"], "handoff-v7")
                self.assertIn(f"<strong>{model_name}</strong>", rendered)
                self.assertNotIn("가용 상태", rendered)
                self.assertNotIn("현재 실행 대안", rendered)

    def test_handoff_v7_rejects_removed_routes_and_fields(self) -> None:
        for model_name, reasoning in (
            ("Luna", "Extra High"), ("Sol", "High"),
            ("Sol", "Extra High"), ("Astra", "Max"),
        ):
            source = current_v7_handoff().replace(
                "- Recommended model: Luna", f"- Recommended model: {model_name}"
            ).replace(
                "- Recommended reasoning: High", f"- Recommended reasoning: {reasoning}"
            )
            self.assert_invalid(source, "unsupported model/reasoning combination")
        for field in ("Route availability: active", "Fallback model: Sol", "Fallback reasoning: High"):
            with self.subTest(field=field):
                with self.assertRaises(RENDERER.HandoffError):
                    RENDERER.parse_handoff(current_v7_handoff().replace(
                        "- Use Ultra: no", f"- {field}\n- Use Ultra: no"
                    ))

    def test_handoff_v7_requires_completion_checklist(self) -> None:
        source = current_v7_handoff()
        start = source.index("### Handoff completion checklist")
        end = source.index("## ", start + 4)
        self.assert_invalid(source[:start] + source[end:], "requires a Handoff completion checklist")

    def test_handoff_v6_supports_task_shape_routing_without_max(self) -> None:
        accepted_routes = {
            ("Luna", "Medium"),
            ("Luna", "High"),
            ("Luna", "Extra High"),
            ("Terra", "Medium"),
            ("Terra", "High"),
            ("Terra", "Extra High"),
            ("Sol", "Light"),
            ("Sol", "Medium"),
            ("Sol", "High"),
            ("Sol", "Extra High"),
            ("Astra", "Medium"),
            ("Astra", "High"),
        }
        self.assertEqual(RENDERER.V6_ROUTING_COMBINATIONS, accepted_routes)

        for model_name, reasoning in sorted(accepted_routes):
            with self.subTest(route=(model_name, reasoning)):
                source = current_v6_handoff().replace(
                    "- Recommended model: Luna",
                    f"- Recommended model: {model_name}",
                ).replace(
                    "- Recommended reasoning: High",
                    f"- Recommended reasoning: {reasoning}",
                )
                if model_name == "Astra":
                    fallback_reasoning = (
                        "High" if reasoning == "Medium" else "Extra High"
                    )
                    source = source.replace(
                        "- Route availability: active",
                        "- Route availability: inactive",
                    ).replace(
                        "- Fallback model: not-applicable",
                        "- Fallback model: Sol",
                    ).replace(
                        "- Fallback reasoning: not-applicable",
                        f"- Fallback reasoning: {fallback_reasoning}",
                    )
                if (model_name, reasoning) == ("Sol", "Extra High"):
                    source = source.replace(
                        "Parser or output safety boundaries become ambiguous.",
                        (
                            "Already at Sol + Extra High; retain it while "
                            "architecture boundaries remain unresolved; evidence E1."
                        ),
                    ).replace(
                        "Architecture direction was read directly.",
                        "Top-route evidence: architecture boundaries are unresolved.",
                    )
                parsed = RENDERER.parse_handoff(source)
                self.assertEqual(
                    parsed["routing"]["Recommended model"],
                    model_name,
                )
                self.assertEqual(
                    parsed["routing"]["Recommended reasoning"],
                    reasoning,
                )

        max_route = current_v6_handoff().replace(
            "- Recommended reasoning: High",
            "- Recommended reasoning: Max",
        )
        self.assert_invalid(max_route, "unsupported model/reasoning combination")

    def test_handoff_v6_marks_astra_inactive_and_renders_fallback(self) -> None:
        astra_medium = current_v6_handoff().replace(
            "- Recommended model: Luna",
            "- Recommended model: Astra",
        ).replace(
            "- Recommended reasoning: High",
            "- Recommended reasoning: Medium",
        ).replace(
            "- Route availability: active",
            "- Route availability: inactive",
        ).replace(
            "- Fallback model: not-applicable",
            "- Fallback model: Sol",
        ).replace(
            "- Fallback reasoning: not-applicable",
            "- Fallback reasoning: High",
        )
        parsed = RENDERER.parse_handoff(astra_medium)
        rendered = RENDERER.render_html(parsed, "a" * 64)

        self.assertEqual(parsed["routing"]["Route availability"], "inactive")
        self.assertIn("<strong>inactive</strong>", rendered)
        self.assertIn("<strong>Sol + High</strong>", rendered)

        self.assert_invalid(
            astra_medium.replace(
                "- Route availability: inactive",
                "- Route availability: active",
            ),
            "Astra Medium must be inactive with Sol High fallback",
        )
        self.assert_invalid(
            astra_medium.replace(
                "- Fallback reasoning: High",
                "- Fallback reasoning: Extra High",
            ),
            "Astra Medium must be inactive with Sol High fallback",
        )
        self.assert_invalid(
            current_v6_handoff().replace(
                "- Fallback model: not-applicable",
                "- Fallback model: Sol",
            ),
            "active non-Astra routes must use not-applicable fallbacks",
        )

    def test_routing_semantics_are_stage_bound_and_constrained(self) -> None:
        unsupported = valid_handoff().replace(
            "Recommended reasoning: High",
            "Recommended reasoning: Extra High",
        )
        self.assert_invalid(unsupported, "unsupported model/reasoning combination")

        wrong_goal = valid_handoff().replace(
            "Goal: Renderer behavior has direct evidence.",
            "Goal: A different outcome.",
        )
        self.assert_invalid(wrong_goal, "must equal the selected stage Outcome")

        wrong_scope = valid_handoff().replace(
            "Change scope: scripts/render_handoff.py and tests/test_render_handoff.py",
            "Change scope: docs only",
        )
        self.assert_invalid(wrong_scope, "must equal the selected stage Scope")

        execution_with_wrong_action = replace_once(
            section_body(valid_handoff(), "Execution plan", "Evidence"),
            "First action: Inspect scripts/render_handoff.py and finish C1.",
            "First action: Start a different action.",
        )
        wrong_first_action = replace_section_body(
            valid_handoff(),
            "Execution plan",
            "Evidence",
            execution_with_wrong_action,
        )
        self.assert_invalid(
            wrong_first_action,
            "top-level First action must equal the selected stage First action",
        )

        ultra_without_evidence = valid_handoff().replace(
            "Use Ultra: no",
            "Use Ultra: yes",
        )
        self.assert_invalid(
            ultra_without_evidence,
            "requires exactly one Ultra evidence line",
        )

        ultra_with_evidence = replace_once(
            ultra_without_evidence,
            "### Next-stage routing",
            "- Ultra evidence: E1\n\n### Next-stage routing",
        )
        ultra_with_evidence = replace_once(
            ultra_with_evidence,
            "Architecture direction was read directly.",
            (
                "Ultra independence: two work items have non-overlapping "
                "ownership and separate verification."
            ),
        )
        self.assertEqual(
            RENDERER.parse_handoff(ultra_with_evidence)["routing"]["Use Ultra"],
            "yes",
        )

        sol_placeholder = valid_handoff().replace(
            "Recommended model: Terra",
            "Recommended model: Sol",
        )

        execution = section_body(valid_handoff(), "Execution plan", "Evidence")
        follow_up = execution.replace(
            "### S1 — Verify renderer",
            "### S2 — Follow-up renderer",
        ).replace("State: ACTIVE", "State: PENDING").replace(
            "| S1-contract-tests |",
            "| S2-contract-tests |",
        )
        skipped_stage = replace_section_body(
            valid_handoff(),
            "Execution plan",
            "Evidence",
            execution + "\n\n" + follow_up,
        ).replace(
            "Current stage: S1 — Verify renderer",
            "Current stage: S2 — Follow-up renderer",
        )
        self.assert_invalid(
            skipped_stage,
            "must name the current unfinished stage",
        )
        sol_placeholder = sol_placeholder.replace(
            "Parser or output safety boundaries become ambiguous.",
            "TBD",
        )
        self.assert_invalid(sol_placeholder, "escalation condition must be observable")

    def test_report_prioritizes_resume_decisions_and_folds_audit_tables(self) -> None:
        rendered = RENDERER.render_html(
            RENDERER.parse_handoff(valid_handoff()),
            "2" * 64,
        )

        self.assertLess(
            rendered.index("<h1>Renderer behavior has direct evidence.</h1>"),
            rendered.index("지금 바로 할 일"),
        )
        self.assertLess(rendered.index("지금 바로 할 일"), rendered.index("C1 · UNVERIFIED"))
        self.assertLess(rendered.index("C1 · UNVERIFIED"), rendered.index("세부 근거"))
        self.assertIn("<section class='section decision-brief' id=resume-brief>", rendered)
        self.assertIn("한눈에 보기", rendered)
        self.assertIn("작업 위치", rendered)
        self.assertIn("모델 추천", rendered)
        self.assertIn("재개 프롬프트", rendered)
        self.assertNotIn("Run first", rendered)
        self.assertIn("<details class='stage-detail current' open>", rendered)
        self.assertIn("<details class=audit-detail>", rendered)
        self.assertIn("--accent:#7823dc", rendered)
        self.assertIn("--canvas:#f5f5f5", rendered)
        self.assertIn("overflow-wrap:anywhere", rendered)
        self.assertIn("@media(max-width:760px)", rendered)
    def test_required_metadata_and_sections_are_rejected_when_missing(
        self,
    ) -> None:
        cases = {
            "metadata": replace_once(
                valid_handoff(),
                "Branch or worktree: main\n",
                "",
            ),
            "section": replace_once(
                valid_handoff(),
                "## Required context\n",
                "",
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                self.assert_invalid(source, "missing")

    def test_pass_and_alignment_evidence_references_are_enforced(self) -> None:
        cases = {
            "invalid evidence result": (
                replace_once(
                    valid_handoff(),
                    (
                        "| E1 | document | PASS | Architecture direction was "
                        "read directly. | docs/ARCHITECTURE.md#handoff |"
                    ),
                    (
                        "| E1 | document | passed | Architecture direction was "
                        "read directly. | docs/ARCHITECTURE.md#handoff |"
                    ),
                ),
                "Result must be PASS, FAIL, or UNVERIFIED",
            ),
            "unknown criterion evidence": (
                replace_once(
                    valid_handoff(),
                    (
                        "| C2 | Durable documentation is aligned | yes | "
                        "PASS | E1 |"
                    ),
                    (
                        "| C2 | Durable documentation is aligned | yes | "
                        "PASS | E99 |"
                    ),
                ),
                "unknown evidence",
            ),
            "pass claim backed by non-pass evidence": (
                replace_once(
                    valid_handoff(),
                    (
                        "| E1 | document | PASS | Architecture direction was "
                        "read directly. | docs/ARCHITECTURE.md#handoff |"
                    ),
                    (
                        "| E1 | document | UNVERIFIED | Architecture direction "
                        "was read directly. | docs/ARCHITECTURE.md#handoff |"
                    ),
                ),
                "PASS references non-PASS evidence",
            ),
            "criterion pass without evidence id": (
                replace_once(
                    valid_handoff(),
                    (
                        "| C2 | Durable documentation is aligned | yes | "
                        "PASS | E1 |"
                    ),
                    (
                        "| C2 | Durable documentation is aligned | yes | "
                        "PASS | reviewed directly |"
                    ),
                ),
                "requires",
            ),
            "stage pass without evidence id": (
                replace_once(
                    valid_handoff(),
                    "| documentation | PASS | E1 |",
                    "| documentation | PASS | reviewed directly |",
                ),
                "requires",
            ),
            "aligned document without evidence id": (
                replace_once(
                    valid_handoff(),
                    (
                        "| Handoff direction | docs/ARCHITECTURE.md#handoff | "
                        "ALIGNED | No update required | E1 |"
                    ),
                    (
                        "| Handoff direction | docs/ARCHITECTURE.md#handoff | "
                        "ALIGNED | No update required | reviewed directly |"
                    ),
                ),
                "requires",
            ),
        }
        for name, (source, message) in cases.items():
            with self.subTest(name=name):
                self.assert_invalid(source, message)

    def test_ready_receipt_requires_current_state_evidence(self) -> None:
        missing = replace_once(
            valid_handoff(),
            "- Evidence: E1\n",
            "",
        )
        self.assert_invalid(
            missing,
            "READY receipt requires evidence in State verification",
        )

        non_passing = replace_once(
            valid_handoff(),
            "- Evidence: E1",
            "- Evidence: E2",
        )
        self.assert_invalid(
            non_passing,
            "State verification PASS references non-PASS evidence",
        )

    def test_monorepo_prompt_must_name_the_scoped_receipt(self) -> None:
        source = valid_handoff().replace(
            "Project scope: .",
            "Project scope: projects/report-automation",
            1,
        )
        prompt = terminal_section_body(source, "New-session prompt")
        prompt = replace_once(
            prompt,
            "Project scope: .",
            "Project scope: projects/report-automation",
        )
        prompt = replace_once(
            prompt,
            "Receipt: docs/HANDOFF.md",
            "Receipt: projects/report-automation/docs/HANDOFF.md",
        )
        source = replace_terminal_section_body(
            source,
            "New-session prompt",
            prompt,
        )
        model = RENDERER.parse_handoff(source)
        self.assertEqual(
            model["metadata"]["Project scope"],
            "projects/report-automation",
        )

        wrong_receipt = replace_once(
            source,
            "Receipt: projects/report-automation/docs/HANDOFF.md",
            "Receipt: docs/HANDOFF.md",
        )
        self.assert_invalid(wrong_receipt, "missing control lines")

    def test_escaped_table_pipe_is_preserved_as_cell_content(self) -> None:
        source = replace_once(
            valid_handoff(),
            "Architecture direction was read directly.",
            r"Architecture command used A \| B.",
        )
        model = RENDERER.parse_handoff(source)
        self.assertEqual(
            model["tables"]["Evidence"]["rows"][0]["Summary"],
            "Architecture command used A | B.",
        )

    def test_last_verified_requires_an_iso_timestamp_with_timezone(self) -> None:
        missing_timezone = replace_once(
            valid_handoff(),
            "Last verified: 2026-07-29T17:00:00+09:00",
            "Last verified: 2026-07-29T17:00:00",
        )
        self.assert_invalid(missing_timezone, "include a timezone")

    def test_every_unfinished_required_criterion_maps_to_a_stage(self) -> None:
        unmapped = replace_once(
            valid_handoff(),
            "| C2 | Durable documentation is aligned | yes | PASS | E1 |",
            (
                "| C2 | Durable documentation is aligned | yes | PASS | E1 |\n"
                "| C3 | Manual output is protected | yes | UNVERIFIED | E2 |"
            ),
        )
        self.assert_invalid(unmapped, "not mapped to a stage")

        unknown = replace_once(valid_handoff(), "Maps to: C1", "Maps to: C99")
        self.assert_invalid(unknown, "unknown criteria")

    def test_stage_requires_each_common_gate_exactly_once(self) -> None:
        missing = replace_once(
            valid_handoff(),
            "| next-input | UNVERIFIED | E2 |\n",
            "",
        )
        self.assert_invalid(missing, "common gates are invalid")

        duplicate = replace_once(
            valid_handoff(),
            "| deliverable | UNVERIFIED | E2 |",
            (
                "| deliverable | UNVERIFIED | E2 |\n"
                "| deliverable | UNVERIFIED | E2 |"
            ),
        )
        self.assert_invalid(duplicate, "duplicate gates or criteria")

    def test_stage_allows_only_one_to_three_prefixed_specific_criteria(
        self,
    ) -> None:
        too_many = replace_once(
            valid_handoff(),
            "| S1-contract-tests | UNVERIFIED | E2 |",
            (
                "| S1-contract-tests | UNVERIFIED | E2 |\n"
                "| S1-html-safety | UNVERIFIED | E2 |\n"
                "| S1-output-safety | UNVERIFIED | E2 |\n"
                "| S1-path-safety | UNVERIFIED | E2 |"
            ),
        )
        self.assert_invalid(too_many, "one to three")

        wrong_prefix = replace_once(
            valid_handoff(),
            "| S1-contract-tests | UNVERIFIED | E2 |",
            "| custom-contract-tests | UNVERIFIED | E2 |",
        )
        self.assert_invalid(wrong_prefix, "must start with S1-")

    def test_pass_and_complete_states_require_all_required_evidence(
        self,
    ) -> None:
        complete = RENDERER.parse_handoff(completed_handoff())
        self.assertEqual(complete["stages"], [])
        self.assertIsNone(complete["prompt"])

        complete_with_unmet_criterion = replace_once(
            replace_once(
                completed_handoff(),
                "No remaining stages.",
                section_body(valid_handoff(), "Execution plan", "Evidence"),
            ),
            "| C1 | The renderer contract is verified | yes | PASS | E2 |",
            (
                "| C1 | The renderer contract is verified | yes | "
                "UNVERIFIED | E2 |"
            ),
        )
        self.assert_invalid(
            complete_with_unmet_criterion,
            "COMPLETE work has unmet required criteria",
        )

        passed_stage_with_unmet_gate = replace_once(
            valid_handoff(),
            "State: ACTIVE",
            "State: PASS",
        )
        self.assert_invalid(
            passed_stage_with_unmet_gate,
            "cannot be PASS with an unmet gate",
        )

        complete_with_active_stage = replace_once(
            completed_handoff(),
            "No remaining stages.",
            section_body(valid_handoff(), "Execution plan", "Evidence"),
        )
        self.assert_invalid(
            complete_with_active_stage,
            "COMPLETE work must have no remaining stages",
        )

        active_without_stage = replace_terminal_section_body(
            replace_once(
                completed_handoff(),
                "Work status: COMPLETE",
                "Work status: ACTIVE",
            ),
            "New-session prompt",
            terminal_section_body(valid_handoff(), "New-session prompt"),
        )
        self.assert_invalid(
            active_without_stage,
            "ACTIVE or BLOCKED work must have at least one remaining stage",
        )

        complete_with_prompt = replace_terminal_section_body(
            completed_handoff(),
            "New-session prompt",
            terminal_section_body(valid_handoff(), "New-session prompt"),
        )
        self.assert_invalid(
            complete_with_prompt,
            "COMPLETE work must use exactly",
        )

        stale_complete = replace_once(
            completed_handoff(),
            "Receipt: READY",
            "Receipt: STALE",
        )
        self.assert_invalid(
            stale_complete,
            "COMPLETE work requires a READY receipt",
        )


    def test_document_conflict_requires_a_blocked_work_state(self) -> None:
        conflict = replace_once(
            valid_handoff(),
            (
                "| Handoff direction | docs/ARCHITECTURE.md#handoff | "
                "ALIGNED | No update required | E1 |"
            ),
            (
                "| Handoff direction | docs/ARCHITECTURE.md#handoff | "
                "CONFLICT | Resolve with the architecture owner | E1 |"
            ),
        )
        self.assert_invalid(conflict, "Work status BLOCKED")

        blocked = replace_once(
            replace_once(
                conflict,
                "Work status: ACTIVE",
                "Work status: BLOCKED",
            ),
            "State: ACTIVE",
            "State: BLOCKED",
        )
        model = RENDERER.parse_handoff(blocked)
        self.assertEqual(model["metadata"]["Work status"], "BLOCKED")

    def test_new_session_prompt_requires_exact_resume_control_lines(self) -> None:
        required_lines = (
            "Handoff action: RESUME",
            "Project scope: .",
            "Receipt: docs/HANDOFF.md",
            "Expected baseline: abc1234",
            "First action: Inspect scripts/render_handoff.py and finish C1.",
            "Begin actual work.",
            "Do not create a new handoff, report, or prompt.",
        )
        for line in required_lines:
            with self.subTest(line=line):
                prompt_body = replace_once(
                    terminal_section_body(
                        valid_handoff(),
                        "New-session prompt",
                    ),
                    line,
                    f"Missing control line: {line}",
                )
                source = replace_terminal_section_body(
                    valid_handoff(),
                    "New-session prompt",
                    prompt_body,
                )
                self.assert_invalid(source, "missing control lines")

        duplicate_invocation = replace_once(
            valid_handoff(),
            "Begin actual work.",
            "$handoff\nBegin actual work.",
        )
        self.assert_invalid(duplicate_invocation)

        conflicting_action = replace_once(
            valid_handoff(),
            "Handoff action: RESUME",
            "Handoff action: RESUME\nHandoff action: PREPARE",
        )
        self.assert_invalid(conflicting_action, "exactly one RESUME action")

    def test_current_start_prompt_separates_session_setup(self) -> None:
        source = current_pause_handoff()
        model = RENDERER.parse_handoff(source)

        self.assertEqual(model["prompt"].splitlines()[0], "$handoff start")
        self.assertEqual(model["continuation"]["Mode"], "PAUSE")
        self.assert_invalid(
            replace_terminal_section_body(
                source,
                "New-session prompt",
                terminal_section_body(source, "New-session prompt").replace(
                    "Begin actual work.",
                    "Recommended model: Terra\nBegin actual work.",
                ),
            ),
            "must not contain session setup recommendations",
        )

    def test_pause_requires_completion_checklist_and_snapshot(self) -> None:
        source = current_pause_handoff()
        self.assert_invalid(
            source.replace(
                "- resume-ready: PASS; E1",
                "- resume-ready: UNVERIFIED; E1",
            ),
            "Handoff completion checklist.resume-ready must be PASS",
        )
        self.assert_invalid(
            source.replace(
                "- HEAD: abc1234",
                "- HEAD: changed",
            ),
            "requires matching HEAD state",
        )
    def test_handoff_v4_uses_no_copyable_prompt_or_continuation(self) -> None:
        source = current_pause_handoff().replace(
            "Format: handoff-v3",
            "Format: handoff-v4",
            1,
        )
        source = replace_once(
            source,
            "### Continuation decision\n\n"
            "- Mode: PAUSE\n"
            "- Branch or worktree: main\n"
            "- Instruction: Resume the recorded current stage.\n\n",
            "",
        )
        source = replace_terminal_section_body(
            source,
            "New-session prompt",
            "No copyable prompt: start reads this receipt directly.",
        )

        model = RENDERER.parse_handoff(source)

        self.assertIsNone(model["prompt"])
        self.assertIsNone(model["continuation"])
        self.assert_invalid(
            source.replace(
                "No copyable prompt: start reads this receipt directly.",
                "```text\n$handoff start\n```",
            ),
            "no-copyable-prompt marker",
        )
    def test_next_work_rejects_delivery_actions(self) -> None:
        self.assert_invalid(
            current_pause_handoff().replace(
                "First action: Inspect scripts/render_handoff.py and finish C1.",
                "First action: Commit the current work and open a PR.",
                1,
            ),
            "First action must name development work, not a delivery action",
        )
        self.assert_invalid(
            replace_once(
                current_pause_handoff(),
                "- Goal: Renderer behavior has direct evidence.",
                "- Goal: Merge the pull request.",
            ),
            "Next-stage routing.Goal must name development work, not a delivery action",
        )

    def test_korean_merge_keyword_respects_word_start_and_action_suffixes(self) -> None:
        for verification in (
            "우선순위 확인 후 approved 수신자와 나머지 알림 규칙을 직접 대조합니다.",
            "검토 결과는 머지않아 확인할 수 있습니다.",
        ):
            with self.subTest(verification=verification):
                source = current_pause_handoff().replace(
                    "Verification: Run the focused unittest file.",
                    f"Verification: {verification}",
                    1,
                )
                RENDERER.parse_handoff(source)

        for verification in (
            "변경을 머지합니다.",
            "승인 뒤 머지를 진행합니다.",
            "검증 후 머지해주세요.",
            "다음 단계에서 머지할 예정입니다.",
        ):
            with self.subTest(verification=verification):
                source = current_pause_handoff().replace(
                    "Verification: Run the focused unittest file.",
                    f"Verification: {verification}",
                    1,
                )
                self.assert_invalid(
                    source,
                    "S1.Verification must name development work, not a delivery action",
                )
    def test_generic_project_plan_does_not_block_handoff(self) -> None:
        root = self.make_project(current_pause_handoff())
        (root / "docs" / "plan.md").write_text(
            "# 제품 로드맵\n\n"
            "- 일반적인 문서 형식도 허용한다.\n"
            "- handoff는 이 내용을 선택적으로만 참고한다.\n",
            encoding="utf-8",
            newline="\n",
        )

        result = self.run_validator(root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    def test_handoff_v5_requires_a_plain_work_summary(self) -> None:
        source = current_v5_handoff()
        model = RENDERER.parse_handoff(source)

        self.assertEqual(
            model["work_summary"]["한 줄 결과"],
            "검색 결과 검증 작업을 완료했습니다.",
        )
        self.assert_invalid(
            source.replace("### 작업 결과 요약\n\n", "", 1),
            "handoff-v5 receipt requires a 작업 결과 요약",
        )
    def test_handoff_v3_requires_a_completion_checklist(self) -> None:
        self.assert_invalid(
            completed_handoff().replace("Format: handoff-v2", "Format: handoff-v3", 1),
            "handoff-v3 receipt requires a Handoff completion checklist",
        )
    def test_cli_refuses_to_overwrite_manual_html(self) -> None:
        root = self.make_project()
        output = root / "docs" / "HANDOFF.html"
        manual = b"<!doctype html>\n<title>Hand edited</title>\n"
        output.write_bytes(manual)

        result = self.run_renderer(root)

        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite non-generated HTML", result.stderr)
        self.assertEqual(output.read_bytes(), manual)

    def test_invalid_input_preserves_prior_generated_output(self) -> None:
        root = self.make_project()
        output = root / "docs" / "HANDOFF.html"
        first = self.run_renderer(root)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()

        invalid = replace_once(
            valid_handoff(),
            "## Evidence\n",
            "",
        )
        (root / "docs" / "HANDOFF.md").write_text(
            invalid,
            encoding="utf-8",
            newline="\n",
        )
        second = self.run_renderer(root)

        self.assertEqual(second.returncode, 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertFalse(
            (root / "docs" / "HANDOFF.html.handoff-render.lock").exists()
        )

    def test_existing_render_lock_fails_closed_without_removing_owner_lock(
        self,
    ) -> None:
        root = self.make_project()
        output = root / "docs" / "HANDOFF.html"
        lock = root / "docs" / "HANDOFF.html.handoff-render.lock"
        lock.write_text("other-renderer-token\n", encoding="utf-8")

        result = self.run_renderer(root)

        self.assertEqual(result.returncode, 2)
        self.assertIn("render lock exists", result.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(
            lock.read_text(encoding="utf-8"),
            "other-renderer-token\n",
        )

    def test_cli_rejects_input_and_output_paths_outside_project_root(
        self,
    ) -> None:
        root = self.make_project()
        outside_source = root.parent / "outside.md"
        outside_source.write_text(valid_handoff(), encoding="utf-8")

        escaped_input = self.run_renderer(root, handoff="../outside.md")
        self.assertEqual(escaped_input.returncode, 2)
        self.assertIn("path escapes project root", escaped_input.stderr)

        outside_output = root.parent / "outside.html"
        escaped_output = self.run_renderer(root, output="../outside.html")
        self.assertEqual(escaped_output.returncode, 2)
        self.assertIn("path escapes project root", escaped_output.stderr)
        self.assertFalse(outside_output.exists())


if __name__ == "__main__":
    unittest.main()
