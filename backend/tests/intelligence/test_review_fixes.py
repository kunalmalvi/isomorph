"""Regression tests for review findings: illustrative experiments, edited hypotheses, rolling guards."""
import pytest

from intelligence.hypothesis_engine.service import experiment_for, is_rolling_context
from intelligence.schemas import Problem, Variable
from intelligence.validation_engine.service import validate
from intelligence.schemas import Hypothesis

CONCEPTS = ["close_feedback_loop", "add_sensing", "add_buffer", "distribute_load", "allocate_resources", "add_dissipation_path"]


def _hyp(spec):
    return Hypothesis(id="h1", statement="s", prediction="p", falsifier="f", category="efficiency", provenance="computation",
                      status="untested", experiment=spec, based_on=[])


@pytest.mark.parametrize("concept", CONCEPTS)
def test_template_experiments_never_reach_supported(concept):
    spec = experiment_for(concept, Problem("p", "t", "s"))
    assert spec["illustrative"] is True
    v = validate(_hyp(spec))
    assert v.outcome == "inconclusive"


def test_rolling_experiments_keep_full_outcome_range():
    p = Problem("p", "t", "s", variables=[Variable("reduction", "%", value=20.0), Variable("thickness", "mm", value=2.0),
                                           Variable("width", "mm", value=1000.0)])
    spec = experiment_for("close_feedback_loop", p)
    assert "illustrative" not in spec


@pytest.mark.parametrize("missing", ["reduction", "thickness", "width"])
def test_rolling_with_unset_value_falls_back_instead_of_raising(missing):
    vals = {"reduction": 20.0, "thickness": 2.0, "width": 1000.0}
    vals[missing] = None
    p = Problem("p", "t", "s", variables=[Variable(k, "%" if k == "reduction" else "mm", value=v) for k, v in vals.items()])
    assert not is_rolling_context(p)
    assert experiment_for("close_feedback_loop", p)["illustrative"] is True
