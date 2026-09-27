"""End-to-end offline flow over the committed sample agent output: parse -> evaluate.

This exercises the same lib code the cmk wiring delegates to (parse the section rows, then
evaluate journeys/worker), so it guards the sample fixture and the producer/consumer contract
without needing a Checkmk site.
"""

from pathlib import Path

from cmk_addons.plugins.synmon.lib import evaluate, parsing
from cmk_addons.plugins.synmon.lib.evaluate import CRIT, OK

_SAMPLE = Path(__file__).resolve().parent / "sample_agent_output.txt"


def _sections(text: str) -> dict[str, list[list[str]]]:
    """Split agent output into {section_name: string_table}, sep(0) (one cell per line)."""
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("<<<<"):  # piggyback host marker (open or close) -> not a section
            continue
        if line.startswith("<<<") and line.endswith(">>>"):
            current = line.strip("<>").split(":")[0]
            sections.setdefault(current, [])
            continue
        if current is not None and line:
            sections[current].append([line])
    return sections


def test_sample_parses_and_evaluates():
    sections = _sections(_SAMPLE.read_text())

    worker = parsing.parse_worker_section(sections["synmon_worker"])
    assert worker is not None
    w_out = evaluate.evaluate_worker(
        worker, {"heartbeat_age_levels": ("fixed", (300.0, 600.0))}, now=2000000100.0
    )
    assert w_out.state == OK
    assert "2 result" in w_out.summary

    journeys = {
        j["journey_name"]: j for j in parsing.parse_journey_section(sections["synmon_journey"])
    }
    assert set(journeys) == {"checkout", "login"}

    # Fresh "now" so staleness does not fire; executor status drives the state.
    now = 2000000100.0
    login = evaluate.evaluate_journey(journeys["login"], {}, now=now)
    checkout = evaluate.evaluate_journey(journeys["checkout"], {}, now=now)

    assert login.state == OK
    assert checkout.state == CRIT
    assert any("TimeoutError" in d for d in checkout.details)
    assert any("checkout-pay.png" in d for d in checkout.details)
