"""The front-page artwork, checked rather than eyeballed.

The drawings under docs/art/ are generated from docs/art/relay.art.json. These
tests run the gates in tools/check_repo_art.py and assert on the receipt they
emit, so a spec edited without re-rendering, a card note the wrapper silently
truncates, or an outcome label wider than its box is a red test rather than a
crooked picture nobody looked at.
"""
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_GATE = _REPO / "tools" / "check_repo_art.py"

GATES = (
    "spec.present",
    "art.matches_spec",
    "art.render_is_deterministic",
    "art.identity_per_repository",
    "art.seed_is_recorded",
    "art.no_local_paths_or_em_dashes",
    "art.spec_words_reach_the_drawing",
    "art.note_survives_the_wrapper",
    "art.return_edge_stays_on_its_row",
    "art.every_illustration_is_shown",
    "art.tagline_stays_inside_its_rule",
    "art.outcome_fits_its_box",
)

DRAWINGS = (
    "docs/art/relay-header.svg",
    "docs/art/accountability-lane.svg",
    "docs/art/endpoint-ladder.svg",
)


def _receipt():
    done = subprocess.run([sys.executable, str(_GATE), "--json"],
                          cwd=str(_REPO), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr or done.stdout
    return json.loads(done.stdout)


def test_every_gate_passes_and_the_receipt_names_what_it_ran():
    receipt = _receipt()
    assert receipt["schema"] == "relay.repo-art/v1"
    assert [c["name"] for c in receipt["checks"]] == list(GATES)
    assert all(c["passed"] for c in receipt["checks"]), \
        [c for c in receipt["checks"] if not c["passed"]]


def test_both_diagrams_and_the_header_are_accounted_for():
    receipt = _receipt()
    assert receipt["specs"] == ["docs/art/relay.art.json"]
    drawn = {out["file"]: out for out in receipt["outputs"]}
    assert set(drawn) == set(DRAWINGS)
    for path, out in drawn.items():
        assert len(out["sha256"]) == 64, path
        assert out["bytes"] > 0, path


def test_a_gate_that_cannot_fail_is_not_a_gate(tmp_path, monkeypatch):
    """Point the outcome-box check at a note too wide for its box and it has to
    complain. Without this, a green suite proves only that the gate ran."""
    sys.path.insert(0, str(_REPO / "tools"))
    import check_repo_art as gate

    spec = json.loads((_REPO / "docs" / "art" / "relay.art.json").read_text("utf-8"))
    spec["flows"][0]["outcomes"][0]["note"] = "x" * 80
    (tmp_path / "relay.art.json").write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.setattr(gate, "ART", tmp_path)
    assert len(gate.check_outcome_fits_its_box([])) == 1
