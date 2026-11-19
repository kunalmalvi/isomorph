"""Phase 9: optional user supplied correlation (Gaussian copula) in monte_carlo."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from experiments import ParameterRecord  # noqa: E402
from experiments.parameters import correlations_from_records  # noqa: E402
from experiments.runners import LIMITATIONS, REGISTRY  # noqa: E402
from experiments.sensitivity import monte_carlo  # noqa: E402

RANGES = {"a": (0.0, 1.0, 4.0), "b": (10.0, 12.0, 20.0), "c": (1.0, 2.0, 3.0)}


def _toy(params, seed):
    return {"y": params["a"] + params["b"] + params["c"]}


@pytest.fixture(autouse=True)
def toy_kind():
    REGISTRY["toy_sum9"] = _toy
    LIMITATIONS["toy_sum9"] = "toy kind for tests"
    yield
    REGISTRY.pop("toy_sum9", None)
    LIMITATIONS.pop("toy_sum9", None)


def _mc(**kw):
    return monte_carlo("toy_sum9", {}, RANGES, ("y",), n=kw.pop("n", 50), seed=kw.pop("seed", 7), **kw)


def _pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    for k, i in enumerate(order):
        r[i] = float(k)
    return r


def test_default_output_unchanged():
    # Stored from the code path before correlations existed (seed 7, triangular, independent draws).
    import random
    rng = random.Random(7)
    expected = []
    for _ in range(3):
        expected.append({p: rng.triangular(lo, hi, nom) for p, (lo, nom, hi) in sorted(RANGES.items())})
    out = _mc(n=3)
    assert out["samples"] == expected
    assert "correlations" not in out
    assert _mc(n=3, correlations={}) == out


@pytest.mark.parametrize("sampling", ["triangular", "uniform"])
@pytest.mark.parametrize("rho", [0.8, -0.6])
def test_empirical_correlation_approaches_rho(sampling, rho):
    out = _mc(n=4000, seed=11, sampling=sampling, correlations={("a", "b"): rho})
    a = [s["a"] for s in out["samples"]]
    b = [s["b"] for s in out["samples"]]
    assert abs(_pearson(a, b) - rho) < 0.08
    assert abs(_pearson(_ranks(a), _ranks(b)) - rho) < 0.08
    c = [s["c"] for s in out["samples"]]
    assert abs(_pearson(a, c)) < 0.08
    assert out["correlations"] == [{"a": "a", "b": "b", "rho": rho}]


def test_marginals_stay_in_range():
    out = _mc(n=2000, correlations={("a", "b"): 0.95, ("b", "c"): 0.3})
    for s in out["samples"]:
        for p, (lo, _, hi) in RANGES.items():
            assert lo <= s[p] <= hi


@pytest.mark.parametrize("bad", [1.0, -1.0, 1.5, float("nan"), "x", True])
def test_invalid_rho_raises(bad):
    with pytest.raises(ValueError):
        _mc(correlations={("a", "b"): bad})


def test_invalid_paths_and_matrix_raise():
    with pytest.raises(ValueError):
        _mc(correlations={("a", "zzz"): 0.5})
    with pytest.raises(ValueError):
        _mc(correlations={("a", "a"): 0.5})
    with pytest.raises(ValueError):
        _mc(correlations={("a", "b"): 0.9, ("b", "c"): 0.9, ("a", "c"): -0.9})


def test_determinism_by_seed():
    c = {("a", "b"): 0.5}
    assert _mc(seed=3, correlations=c)["samples"] == _mc(seed=3, correlations=c)["samples"]
    assert _mc(seed=3, correlations=c)["samples"] != _mc(seed=4, correlations=c)["samples"]


def test_record_correlation_is_opt_in():
    def rec(name, **kw):
        return ParameterRecord(name=name, unit="u", nominal=1.0, low=0.5, high=2.0, kind="assumption", **kw)
    assert rec("K").correlations == {}
    recs = {"K": rec("K"), "n": rec("n")}
    assert correlations_from_records(recs) == {}
    recs = {"K": rec("K", correlations={"n": -0.5}), "n": rec("n")}
    assert correlations_from_records(recs, {"K": "material.K", "n": "material.n"}) == {("material.K", "material.n"): -0.5}
    with pytest.raises(ValueError):
        rec("K", correlations={"n": 1.0})
    with pytest.raises(ValueError):
        correlations_from_records({"K": rec("K", correlations={"zz": 0.2})})
    assert ParameterRecord.from_dict(recs["K"].to_dict()) == recs["K"]
