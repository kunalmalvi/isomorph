import pytest

from ai_providers.base import (CompletionRequest, CompletionResult, Provider, ProviderError, ProviderSchemaError,
                               ProviderTransportError)
from ai_providers.local import LocalProvider
from intelligence.perception import perceive_text, classify_unknown_roles, resolve_unknown_role
from intelligence.schemas import ROLES


def _nodes(text):
    r = perceive_text(text, "t")
    return r, {n.label: n for n in r.problem.graph.nodes}


def test_head_noun_fallback_resolves_via_pump():
    r, nodes = _nodes("The coolant circulation pump moves the fluid.")
    assert list(nodes) == ["pump", "fluid"]  # modifiers are absorbed, not split into a spurious 'coolant circulation'
    assert nodes["pump"].role == "actuator" and nodes["pump"].span == "coolant circulation pump"
    assert resolve_unknown_role(["coolant", "circulation", "pump"]) == ("actuator", "head_noun")


def test_compound_tail_and_hyphen_morphology():
    assert resolve_unknown_role(["floodgate"]) == ("regulator", "morphology")
    assert resolve_unknown_role(["heat-exchanger"]) == ("transformer", "morphology") or \
        resolve_unknown_role(["heat-exchanger"])[1] == "morphology"
    assert resolve_unknown_role(["pump-turbine"]) == ("transformer", "morphology")


def test_plural_inflection_resolves():
    assert resolve_unknown_role(["pumps"]) == ("actuator", "morphology")


def test_knowledge_index_used_when_lexicon_misses():
    # 'capital' appears only on buffer-role nodes in the seed knowledge base (bank capital), not in the lexicon
    res = resolve_unknown_role(["reserve", "capital"])
    assert res is not None and res[1] == "knowledge_index" and res[0] in ROLES


def test_knowledge_index_result_is_marked_low_confidence_inference():
    r, nodes = _nodes("The bank capital is high. The goal is to keep it stable.")
    n = nodes["bank capital"]
    assert n.role is not None and n.attrs["role_source"] in ("knowledge_index", "head_noun", "morphology")
    assert n.confidence < 0.7
    inf = [i for i in r.inferences if "bank capital" in i["statement"]]
    assert inf and inf[0]["provenance"] == "computation" and "guess" in inf[0]["statement"]
    assert inf[0]["span"] and inf[0]["confidence"] < 0.7


def test_context_inference_from_verb_cue():
    r, nodes = _nodes("The zorblat controls the valve.")
    n = nodes["zorblat"]
    assert n.role == "controller" and n.attrs["role_source"] == "context" and n.confidence <= 0.3
    inf = [i for i in r.inferences if i.get("source") == "context"]
    assert inf and "verb 'controls'" in inf[0]["statement"] and inf[0]["span"]
    _, nodes = _nodes("The zorblat measures the temperature.")
    assert nodes["zorblat"].role == "sensor"


def test_context_never_overrides_lexicon_role():
    _, nodes = _nodes("The pump controls the valve.")
    assert nodes["pump"].role == "actuator" and "role_source" not in nodes["pump"].attrs


def test_unknown_terms_stay_none_when_nothing_matches():
    r, nodes = _nodes("The frobnicator touches the zorblat.")
    assert nodes["frobnicator"].role is None and nodes["zorblat"].role is None
    assert any("frobnicator" in u for u in r.unknowns)
    assert resolve_unknown_role(["frobnicator"]) is None


def test_lexicon_roles_unchanged():
    _, nodes = _nodes("The motor drives the rolls. The rolls reduce the strip.")
    assert nodes["motor"].role == "actuator" and nodes["strip"].role == "medium"


# ------------------------------------------------------------------ optional AI classification
class FakeProvider(Provider):
    name = "fake"
    provenance = "ai_hypothesis"
    model = "fake-1"

    def __init__(self, parsed=None, exc=None):
        super().__init__()
        self.parsed, self.exc, self.calls = parsed, exc, []

    def complete(self, req: CompletionRequest) -> CompletionResult:
        self.calls.append(req)
        if self.exc:
            raise self.exc
        return CompletionResult("", self.parsed, self.name, self.model, self.provenance)


def _unknown_result():
    return perceive_text("The frobnicator touches the zorblat.", "t")


def test_ai_classifies_only_unknown_entities_and_marks_hypothesis():
    r = perceive_text("The frobnicator touches the zorblat. The pump moves the water.", "t")
    p = FakeProvider({"roles": [{"label": "frobnicator", "role": "sensor"}, {"label": "zorblat", "role": "buffer"}]})
    classify_unknown_roles(r, p)
    nodes = {n.label: n for n in r.problem.graph.nodes}
    assert nodes["frobnicator"].role == "sensor" and nodes["zorblat"].role == "buffer"
    assert nodes["frobnicator"].attrs["role_source"] == "ai_provider"
    assert nodes["pump"].role == "actuator"
    assert "pump" not in p.calls[0].prompt
    assert any(i.get("source") == "ai_provider" and i["provenance"] == "ai_hypothesis" for i in r.inferences)


def test_ai_rejects_role_outside_enum():
    r = _unknown_result()
    p = FakeProvider({"roles": [{"label": "frobnicator", "role": "wizard"}]})
    with pytest.raises(ProviderSchemaError):
        classify_unknown_roles(r, p)
    assert all(n.role is None for n in r.problem.graph.nodes)


def test_ai_rejects_label_not_asked_about():
    r = _unknown_result()
    p = FakeProvider({"roles": [{"label": "invented thing", "role": "sensor"}]})
    with pytest.raises(ProviderSchemaError):
        classify_unknown_roles(r, p)


def test_ai_rejects_malformed_output():
    r = _unknown_result()
    with pytest.raises(ProviderSchemaError):
        classify_unknown_roles(r, FakeProvider({"nope": 1}))
    with pytest.raises(ProviderSchemaError):
        classify_unknown_roles(r, FakeProvider(None))


def test_ai_provider_failure_raises_and_changes_nothing():
    r = _unknown_result()
    with pytest.raises(ProviderTransportError):
        classify_unknown_roles(r, FakeProvider(exc=ProviderTransportError("down")))
    assert all(n.role is None for n in r.problem.graph.nodes)


def test_ai_not_called_when_nothing_unknown():
    r = perceive_text("The pump moves the water.", "t")
    p = FakeProvider({"roles": []})
    classify_unknown_roles(r, p)
    assert p.calls == []


def test_local_provider_cannot_classify_and_perception_default_is_off():
    r = _unknown_result()
    with pytest.raises(ProviderError):
        classify_unknown_roles(r, LocalProvider())
    # perceive_text itself never calls a provider
    assert all(n.role is None for n in _unknown_result().problem.graph.nodes)


def test_modifier_absorption_does_not_swallow_subject_before_a_verb():
    _, nodes = _nodes("The mash tun heats the wort.")
    assert "mash tun" in nodes and nodes["mash tun"].span == "mash tun"
