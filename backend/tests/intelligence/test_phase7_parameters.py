"""Phase 7: parameter records, sensitivity analysis, bite limit fix and the uncertainty block of the roller demo."""
import json
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from experiments import ParameterRecord, run_experiment  # noqa: E402
from experiments import runners  # noqa: E402
from experiments.runners import MATERIALS, REGISTRY, max_bite_draft  # noqa: E402
from experiments.sensitivity import monte_carlo, one_at_a_time  # noqa: E402
from intelligence.constraint_engine import service as ce  # noqa: E402


def rec(**kw):
    d = dict(name="x", unit="mm", nominal=1.0, low=0.5, high=2.0, kind="assumption", source="s", range_basis="analyst_judgment", confidence="low")
    d.update(kw)
    return ParameterRecord(**d)


# ------------------------------------------------------------------ records
def test_record_validation():
    with pytest.raises(ValueError):
        rec(low=2.0, nominal=1.0, high=3.0)
    with pytest.raises(ValueError):
        rec(nominal=float("nan"))
    with pytest.raises(ValueError):
        rec(high=float("inf"))
    with pytest.raises(ValueError):
        rec(kind="handbook", source="  ")
    with pytest.raises(ValueError):
        rec(confidence="certain")
    with pytest.raises(ValueError):
        rec(kind="guess")
    assert rec().verification == "unverified_no_network"


def test_record_round_trip():
    r = rec(kind="handbook", notes="n")
    assert ParameterRecord.from_dict(r.to_dict()) == r


# ------------------------------------------------------------------ sensitivity
def _toy(params, seed):
    return {"y": 10.0 * params["a"] + 1.0 * params["b"] + params.get("m", {}).get("k", 0.0)}


@pytest.fixture(autouse=True)
def toy_kind():
    """Register a toy kind for the test and remove it afterwards so other tests see the real registry."""
    REGISTRY["toy_linear"] = _toy
    runners.LIMITATIONS["toy_linear"] = "toy kind for tests"
    yield
    REGISTRY.pop("toy_linear", None)
    runners.LIMITATIONS.pop("toy_linear", None)


RANGES = {"a": (0.0, 1.0, 2.0), "b": (0.0, 1.0, 2.0)}


def test_tornado_order_and_values():
    rows = one_at_a_time("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, "y")
    assert [r["parameter"] for r in rows] == ["a", "b"]
    assert rows[0]["swing"] == pytest.approx(20.0) and rows[1]["swing"] == pytest.approx(2.0)
    assert rows[0]["metric_at_nominal"] == pytest.approx(11.0)


def test_dotted_material_path():
    rows = one_at_a_time("toy_linear", {"a": 1.0, "b": 1.0, "m": {"k": 0.0}}, {"m.k": (0.0, 5.0, 100.0)}, "y")
    assert rows[0]["metric_at_high"] - rows[0]["metric_at_low"] == pytest.approx(100.0)
    f = one_at_a_time("strip_rolling_model", {"reduction": 0.2, "material": "copper"}, {"material.K": (200.0, 315.0, 400.0)}, "roll_force_kn")
    assert f[0]["metric_at_high"] > f[0]["metric_at_low"]
    assert MATERIALS["copper"]["K"] == 315.0  # the shared table is not mutated


def test_monte_carlo_deterministic_and_bounded():
    a = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=100, seed=3)
    b = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=100, seed=3)
    c = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=100, seed=4)
    assert a == b and a != c
    for s in a["samples"]:
        assert all(RANGES[k][0] <= v <= RANGES[k][2] for k, v in s.items())
    m = a["metrics"]["y"]
    assert m["min"] <= m["p05"] <= m["median"] <= m["p95"] <= m["max"]
    assert 0.0 <= m["min"] and m["max"] <= 22.0
    u = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=50, seed=3, sampling="uniform")
    assert u["sampling"] == "uniform"


def test_pass_fraction():
    always = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=40, seed=1, predicate=lambda m: True)
    never = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=40, seed=1, predicate=lambda m: False)
    half = monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=200, seed=1, predicate=lambda m: m["y"] <= 11.0)
    assert always["pass_fraction"] == 1.0 and never["pass_fraction"] == 0.0
    assert 0.0 < half["pass_fraction"] < 1.0
    assert monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=5)["pass_fraction"] is None
    with pytest.raises(ValueError):
        monte_carlo("toy_linear", {"a": 1.0, "b": 1.0}, RANGES, ("y",), n=5, sampling="bad")


# ------------------------------------------------------------------ bite limit
def test_bite_helper_agrees_with_validator():
    from intelligence.schemas import Constraint
    for R, mu, h0, red in ((100.0, 0.08, 2.0, 0.2), (100.0, 0.05, 2.0, 0.2), (75.0, 0.12, 3.0, 0.3)):
        limit = max_bite_draft(R, mu)
        values = {"thickness_mm": h0, "reduction_fraction": red, "roll_radius_mm": R, "friction": mu}
        out, detail = ce._bite(values, {})
        assert (out == ce.SATISFIED) == (h0 * red <= limit + 1e-12)
        assert f"{limit:.3f}" in detail
        m = run_experiment("strip_rolling_model", {"reduction": red, "thickness_mm": h0, "roll_radius_mm": R, "friction": mu}).metrics
        assert m["max_bite_draft_mm"] == pytest.approx(limit)


def test_bite_limit_is_two_roll_geometry():
    for mu in (0.01, 0.03, 0.06, 0.1):
        assert max_bite_draft(100.0, mu) == pytest.approx(2 * 100.0 * (1 - math.cos(math.atan(mu))))
        if mu <= 0.06:
            assert abs(max_bite_draft(100.0, mu) - mu * mu * 100.0) / (mu * mu * 100.0) < 0.01
    # the earlier limit R*(1-cos) was half this value
    assert max_bite_draft(100.0, 0.12) == pytest.approx(2 * 100.0 * (1 - 1 / math.sqrt(1 + 0.12 ** 2)))


# ------------------------------------------------------------------ materials and demo
def test_materials_have_provenance():
    for name, m in MATERIALS.items():
        assert m["source"] and m["confidence"] in ("high", "medium", "low")
        assert m["verification"] == "unverified_no_network"
        assert m["K_low"] <= m["K"] <= m["K_high"] and m["n_low"] <= m["n"] <= m["n_high"]
        assert m["range_basis"] in ("source", "analyst_judgment")
    assert "ASSUMED placeholder" not in MATERIALS["silver"]["source"]
    assert MATERIALS["silver"]["confidence"] == "low"


def test_demo_records():
    with open(os.path.join(ROOT, "data", "demo", "roller_problem.json"), encoding="utf-8") as f:
        spec = json.load(f)
    recs = [ParameterRecord.from_dict(r) for r in spec["parameter_records"]]
    names = {r.name for r in recs}
    assert {"friction", "roll_radius_mm", "mill_modulus_kn_per_mm", "roll_force_limit_kn", "tolerance_mm"} <= names
    for r in recs:
        assert r.verification
        if r.kind != "user_input":
            assert r.source and r.confidence
    for r in recs:
        if r.name in spec["parameters"]:
            assert spec["parameters"][r.name] == r.nominal
    fr = next(r for r in recs if r.name == "friction")
    assert fr.low == 0.03 and fr.high == 0.12


@pytest.fixture(scope="module")
def demo_runs():
    import run_demo
    from intelligence.learning_engine import MemoryStore
    r1 = run_demo.run_demo(None, "copper", MemoryStore())
    r2 = run_demo.run_demo(None, "copper", MemoryStore())
    t = run_demo.material_table(r1["params"], r1["records"])
    return run_demo, r1, r2, t


def test_demo_uncertainty_output(demo_runs):
    run_demo, r1, r2, t = demo_runs
    js = run_demo.to_json(r1, t)
    assert "uncertainty" in js and "analysis_status" in js and "parameter_records" in js
    assert "not certified" in js["analysis_status"]
    for mat in ("copper", "silver"):
        u = js["uncertainty"][mat]
        assert 0.0 <= u["single_pass"]["pass_fraction_force_and_bite"] <= 1.0
        assert u["tornado_single_pass_force"][0]["swing_kn"] >= u["tornado_single_pass_force"][-1]["swing_kn"]
        assert "conclusions" in u
    report = run_demo.render_report(r1, t)
    assert "not certified" in report and "Parameter provenance" in report and "unverified_no_network" in report
    assert "—" not in report
    assert round(r1["search"].matches[0].score, 1) == 37.5 and r1["search"].matches[0].system_id == "arch_vav_zone_control"


def test_demo_deterministic(demo_runs):
    run_demo, r1, r2, t = demo_runs
    assert json.dumps(r1["uncertainty"], sort_keys=True) == json.dumps(r2["uncertainty"], sort_keys=True)
    assert run_demo.render_report(r1, t) == run_demo.render_report(r2, t)
