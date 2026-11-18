"""Deterministic experiment runners. Each takes (params, seed) and returns a metrics dict.

Every runner states its model and limitations in LIMITATIONS. All randomness comes from random.Random(seed).
"""
import math
import random
from typing import Any, Callable, Dict, List, Optional

from intelligence.schemas import Graph, ExperimentRun
from intelligence.graph_engine import max_flow
from .common import CODE_VERSION, config_hash, MODEL_DISCLAIMER
from .linear_solver import gaussian_solve, conjugate_gradient

LIMITATIONS: Dict[str, str] = {}
REGISTRY: Dict[str, Callable[[dict, int], Dict[str, Any]]] = {}


def runner(kind: str, limitation: str):
    def deco(fn):
        REGISTRY[kind] = fn
        LIMITATIONS[kind] = limitation + " " + MODEL_DISCLAIMER
        return fn
    return deco


def available_kinds() -> List[str]:
    return sorted(REGISTRY)


def run_experiment(kind: str, params: dict, seed: int = 0) -> ExperimentRun:
    if kind not in REGISTRY:
        raise KeyError(f"unknown experiment kind {kind}")
    cfg = {"kind": kind, "params": params, "seed": seed}
    metrics = REGISTRY[kind](params, seed)
    return ExperimentRun(seed=seed, config_hash=config_hash(cfg), code_version=CODE_VERSION, metrics=metrics,
                         kind=kind, limitations=LIMITATIONS[kind])


# ------------------------------------------------------------ load distribution
def solve_load_distribution(graph: Graph, source: str, sink: str, injection: float = 1.0, use_cg: bool = False) -> Dict[str, Any]:
    """Nodal analysis: edge weight = conductance, sink grounded, injection at source.

    Solves L v = b for node potentials, then edge flow = w * (v_u - v_v). Parallel edges allowed.
    Edges are treated as undirected conductances (potential driven flow), as for a resistor or pipe network.
    """
    ids = [n.id for n in graph.nodes]
    if source not in ids or sink not in ids or source == sink:
        raise ValueError("source and sink must be distinct nodes of the graph")
    free = [i for i in ids if i != sink]
    idx = {n: k for k, n in enumerate(free)}
    n = len(free)
    L = [[0.0] * n for _ in range(n)]
    for e in graph.edges:
        if e.source == e.target:
            continue
        w = e.weight
        for a, b in ((e.source, e.target), (e.target, e.source)):
            if a in idx:
                L[idx[a]][idx[a]] += w
                if b in idx:
                    L[idx[a]][idx[b]] -= w
    b = [0.0] * n
    b[idx[source]] = injection
    v = conjugate_gradient(L, b) if use_cg else gaussian_solve(L, b)
    pot = {nid: (v[idx[nid]] if nid in idx else 0.0) for nid in ids}
    flows = {e.id: e.weight * (pot[e.source] - pot[e.target]) for e in graph.edges if e.source != e.target}
    util = {k: abs(f) for k, f in flows.items()}
    mx = max(util.values()) if util else 0.0
    mean = sum(util.values()) / len(util) if util else 0.0
    return {"potentials": pot, "flows": flows, "max_edge_flow": mx, "mean_edge_flow": mean,
            "imbalance": (mx / mean) if mean else 0.0,
            "effective_resistance": pot[source] / injection if injection else 0.0}


@runner("load_distribution", "Linear potential-driven flow; ignores nonlinearity, directionality and dynamics.")
def _load_distribution(params: dict, seed: int) -> Dict[str, Any]:
    g = Graph.from_dict(params["graph"])
    r = solve_load_distribution(g, params["source"], params["sink"], params.get("injection", 1.0), params.get("use_cg", False))
    return {"max_edge_flow": r["max_edge_flow"], "imbalance": r["imbalance"], "effective_resistance": r["effective_resistance"]}


# ------------------------------------------------------------------ network flow
@runner("network_flow", "Static maximum flow on given capacities; no time dimension or costs.")
def _network_flow(params: dict, seed: int) -> Dict[str, Any]:
    g = Graph.from_dict(params["graph"])
    val, flow = max_flow(g, params["source"], params["sink"])
    sat = sorted(e.id for e in g.edges if e.weight > 0 and abs(flow.get(e.id, 0.0) - e.weight) < 1e-9)
    return {"max_flow": val, "saturated_edges": len(sat), "saturated_edge_ids": sat}


# ---------------------------------------------------------------- resource allocation
@runner("resource_allocation", "Concave utility model with random instances per seed; real benefits are unknown.")
def _resource_allocation(params: dict, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    n = params.get("activities", 6)
    budget = params.get("budget", 100.0)
    gains = [rng.uniform(5, 20) for _ in range(n)]
    scales = [rng.uniform(5, 40) for _ in range(n)]
    util = lambda i, x: gains[i] * (1.0 - math.exp(-x / scales[i]))
    if params["policy"] == "equal":
        alloc = [budget / n] * n
    elif params["policy"] == "marginal":
        step = budget / 1000.0
        alloc = [0.0] * n
        for _ in range(1000):
            i = max(range(n), key=lambda k: (util(k, alloc[k] + step) - util(k, alloc[k]), -k))
            alloc[i] += step
    else:
        raise ValueError("policy must be equal or marginal")
    total = sum(util(i, alloc[i]) for i in range(n))
    return {"total_utility": total, "spent": sum(alloc)}


# ----------------------------------------------------------------------- queueing
@runner("queueing", "M/M/c/K event simulation with exponential times; real arrivals are rarely Poisson.")
def _queueing(params: dict, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    lam, mu, c, K = params["arrival_rate"], params["service_rate"], params["servers"], params["capacity"]
    n_jobs = params.get("jobs", 5000)
    t, arrivals = 0.0, []
    for _ in range(n_jobs):
        t += rng.expovariate(lam)
        arrivals.append(t)
    free_at = [0.0] * c  # next time each server is free
    in_system_ends: List[float] = []
    waits, lost, busy = [], 0, 0.0
    for a in arrivals:
        in_system_ends = [e for e in in_system_ends if e > a]
        if len(in_system_ends) >= K:
            lost += 1
            continue
        k = min(range(c), key=lambda s: (free_at[s], s))
        start = max(a, free_at[k])
        svc = rng.expovariate(mu)
        free_at[k] = start + svc
        busy += svc
        waits.append(start - a)
        in_system_ends.append(start + svc)
    horizon = max(free_at) if free_at else 1.0
    waits_sorted = sorted(waits)
    p95 = waits_sorted[int(0.95 * (len(waits_sorted) - 1))] if waits_sorted else 0.0
    return {"mean_wait": sum(waits) / len(waits) if waits else 0.0, "p95_wait": p95,
            "loss_fraction": lost / n_jobs, "utilization": busy / (c * horizon) if horizon else 0.0}


# ---------------------------------------------------------------- feedback regulation
@runner("feedback_regulation", "First order plant with random disturbance; real plants have delays and nonlinearity beyond this.")
def _feedback(params: dict, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    mode = params["mode"]  # open_loop | feedback | feedforward
    n = params.get("steps", 400)
    a, target, gain = params.get("plant_decay", 0.8), params.get("target", 1.0), params.get("gain", 0.5)
    sigma = params.get("disturbance_sigma", 0.1)
    delay = params.get("measurement_delay", 1)
    y, u = target, target * (1 - a)
    hist, errs, dist_hist = [y], [], [0.0]
    for k in range(n):
        d = 0.8 * dist_hist[-1] + rng.gauss(0, sigma)  # autocorrelated disturbance
        dist_hist.append(d)
        if mode == "feedback":
            meas = hist[max(0, len(hist) - 1 - delay)]
            u = target * (1 - a) + gain * (target - meas)
        elif mode == "feedforward":
            u = target * (1 - a) - 0.9 * dist_hist[-1]
        else:
            u = target * (1 - a)
        y = a * y + u + d
        hist.append(y)
        errs.append(y - target)
    rms = math.sqrt(sum(e * e for e in errs) / len(errs))
    return {"rms_error": rms, "max_abs_error": max(abs(e) for e in errs)}


# ----------------------------------------------------------------- damped oscillator
@runner("damped_oscillator", "Linear mass-spring-damper integrated with semi-implicit Euler; ideal parts only.")
def _oscillator(params: dict, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    x, v = rng.uniform(0.8, 1.2), 0.0
    m, k, c, dt = params.get("mass", 1.0), params.get("stiffness", 4.0), params["damping"], params.get("dt", 0.005)
    peak_over, settle, t = 0.0, 0.0, 0.0
    for _ in range(int(params.get("duration", 20.0) / dt)):
        a = (-k * x - c * v) / m
        v += a * dt
        x += v * dt
        t += dt
        peak_over = max(peak_over, abs(x))
        if abs(x) > 0.02:
            settle = t
    return {"settling_time": settle, "peak_abs_displacement": peak_over}


# ------------------------------------------------------------------ strip rolling
MATERIALS = {
    # K (MPa) and n of a power-law flow curve sigma = K * eps^n (true stress, true strain). Every value was recalled
    # without network access, so none is checked against its source (verification: unverified_no_network).
    # None of this is certified data. Replace with measured tensile or compression data for the actual strip.
    "copper": {
        "K": 315.0, "n": 0.54, "K_low": 268.0, "K_high": 362.0, "n_low": 0.46, "n_high": 0.62,
        "condition": "annealed",
        "source": "recalled from the strength coefficient and strain hardening exponent tables in Dieter, Mechanical Metallurgy (annealed copper)",
        "range_basis": "analyst_judgment", "confidence": "medium", "verification": "unverified_no_network",
        "notes": "Range is plus or minus 15 percent on K and n, an analyst judgment: temper, purity and prior cold work all shift the curve.",
    },
    "silver": {
        "K": 320.0, "n": 0.40, "K_low": 250.0, "K_high": 450.0, "n_low": 0.30, "n_high": 0.50,
        "condition": "annealed fine silver",
        "source": "estimate derived from a recalled annealed fine silver ultimate tensile strength of about 125 to 170 MPa and n of about 0.4",
        "range_basis": "analyst_judgment", "confidence": "low", "verification": "unverified_no_network",
        "notes": ("At the onset of necking true strain equals n and true stress equals K * n^n. With UTS 125 to 170 MPa, "
                  "true stress = UTS * exp(n) = about 187 to 254 MPa, and n^n = 0.693 for n = 0.4, so K = about 270 to 366 MPa; "
                  "nominal K is set to 320 MPa. The range 250 to 450 MPa is widened for temper and purity. Supply measured tensile data."),
    },
}


def max_bite_draft(R: float, mu: float) -> float:
    """Largest draft a two-roll mill can bite: dh_max = 2*R*(1 - cos(atan(mu))) = 2*R*(1 - 1/sqrt(1 + mu^2)), about mu^2 * R.

    The contact length L = sqrt(R*dh) in roll_pass uses the same geometry. A copy of this formula lives in
    intelligence/constraint_engine/service.py (_bite); a test asserts the two agree. The earlier limit R*(1 - 1/sqrt(1+mu^2))
    was half this value, a conservative error.
    """
    return 2.0 * R * (1.0 - 1.0 / math.sqrt(1.0 + mu * mu))


def mean_flow_stress(K: float, n: float, e_a: float, e_b: float) -> float:
    """Mean of K*e^n over true strain interval [e_a, e_b]."""
    if e_b <= e_a:
        return K * e_b ** n
    return K * (e_b ** (n + 1) - e_a ** (n + 1)) / ((n + 1) * (e_b - e_a))


def roll_pass(h0: float, h1: float, width: float, R: float, mu: float, K: float, n: float, e_prev: float = 0.0) -> Dict[str, float]:
    """Simplified single cold-rolling pass (plane strain, no roll flattening, no tension).

    contact length L = sqrt(R*dh); mean flow stress from work hardening law; plane strain factor 1.155;
    mean pressure p = sigma' * (1 + mu*L/(h0+h1)); force F = p*w*L (N, with mm and MPa); torque ~ 0.5*F*L per roll.
    """
    dh = h0 - h1
    e_b = e_prev + math.log(h0 / h1)
    sig = 1.155 * mean_flow_stress(K, n, e_prev, e_b)
    L = math.sqrt(R * dh)
    p = sig * (1.0 + mu * L / (h0 + h1))
    F = p * width * L
    max_draft = max_bite_draft(R, mu)
    return {"exit_thickness_mm": h1, "draft_mm": dh, "contact_length_mm": L, "mean_pressure_mpa": p,
            "roll_force_kn": F / 1000.0, "torque_per_roll_nm": 0.5 * F * L / 1000.0, "max_bite_draft_mm": max_draft,
            "bite_ok": dh <= max_draft + 1e-12, "strain_after": e_b}


def _mat(params: dict) -> Dict[str, float]:
    m = params.get("material", "copper")
    if isinstance(m, dict):
        return m
    return MATERIALS[m]


@runner("strip_rolling_model", "Single deterministic pass model; see roll_pass docstring for omitted effects.")
def _strip_model(params: dict, seed: int) -> Dict[str, Any]:
    mat = _mat(params)
    h0 = params.get("thickness_mm", 2.0)
    h1 = h0 * (1.0 - params["reduction"])
    r = roll_pass(h0, h1, params.get("width_mm", 50.0), params.get("roll_radius_mm", 100.0), params.get("friction", 0.08),
                  mat["K"], mat["n"])
    return r


@runner("strip_rolling_passes", "Multi-pass schedule with equal true strain per pass and cumulative work hardening.")
def _strip_passes(params: dict, seed: int) -> Dict[str, Any]:
    mat = _mat(params)
    h0 = params.get("thickness_mm", 2.0)
    total = params["reduction"]
    passes = params["passes"]
    hf = h0 * (1.0 - total)
    ratio = (hf / h0) ** (1.0 / passes)
    h, e, forces, bite = h0, 0.0, [], True
    for _ in range(passes):
        h_next = h * ratio
        r = roll_pass(h, h_next, params.get("width_mm", 50.0), params.get("roll_radius_mm", 100.0),
                      params.get("friction", 0.08), mat["K"], mat["n"], e)
        forces.append(r["roll_force_kn"])
        bite = bite and r["bite_ok"]
        e, h = r["strain_after"], h_next
    return {"peak_roll_force_kn": max(forces), "total_roll_force_kn": sum(forces), "all_passes_bite_ok": bite,
            "passes": passes}


@runner("strip_rolling_gauge", "Elastic mill stretch plus power-law flow stress; disturbances are Gaussian with AR(1) persistence 0.95 and a random-walk gap drift; mill modulus (default 200 kN/mm, a small lab mill) is an ASSUMPTION; real mills have more dynamics.")
def _strip_gauge(params: dict, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    mat = _mat(params)
    h0n = params.get("thickness_mm", 2.0)
    width, R, mu = params.get("width_mm", 50.0), params.get("roll_radius_mm", 100.0), params.get("friction", 0.08)
    M = params.get("mill_modulus_kn_per_mm", 200.0)
    target = h0n * (1.0 - params["reduction"])
    n_coils = params.get("coils", 200)
    sig_h, sig_k, sig_m = params.get("entry_sigma", 0.02), params.get("hardness_sigma", 0.05), params.get("meas_sigma_mm", 0.002)
    mode, delay, kgain = params["mode"], params.get("delay_coils", 2), params.get("gain", 0.3)

    def force(h0, h1, Kf):
        return roll_pass(h0, h1, width, R, mu, Kf, mat["n"])["roll_force_kn"]

    def exit_for(S, h0, Kf):
        h1 = max(S, 0.05 * h0)
        for _ in range(60):  # h1 = S + F/M by fixed point
            nh = max(S + force(h0, min(h1, h0 * 0.999), Kf) / M, 0.05 * h0)
            if abs(nh - h1) < 1e-10:
                break
            h1 = nh
        return h1

    # screw setting S chosen so nominal exit equals target (gauge-meter calibration)
    S = target - force(h0n, target, mat["K"]) / M
    drift_sigma = params.get("drift_sigma_mm", 0.002)
    phi = params.get("persistence", 0.95)
    dh_state = dk_state = 0.0
    exits, peaks, meas_hist = [], [], []
    for i in range(n_coils):
        S += rng.gauss(0, drift_sigma)  # thermal and wear drift of the roll gap
        # entry thickness and hardness deviations persist along the strip (AR(1)); this persistence is an assumption
        dh_state = phi * dh_state + math.sqrt(1 - phi * phi) * rng.gauss(0, sig_h)
        dk_state = phi * dk_state + math.sqrt(1 - phi * phi) * rng.gauss(0, sig_k)
        h0 = h0n * (1 + dh_state)
        Kf = mat["K"] * (1 + dk_state)
        h1 = exit_for(S, h0, Kf)
        exits.append(h1)
        peaks.append(force(h0, h1, Kf))
        meas_hist.append(h1 + rng.gauss(0, sig_m))
        if mode == "feedback" and i >= delay:
            S -= kgain * (meas_hist[i - delay] - target)
    dev = [e - target for e in exits]
    tol = params.get("tolerance_mm", 0.02)
    mean = sum(dev) / len(dev)
    std = math.sqrt(sum((d - mean) ** 2 for d in dev) / len(dev))
    return {"exit_std_mm": std, "max_abs_dev_mm": max(abs(d) for d in dev), "rms_dev_mm": math.sqrt(sum(d * d for d in dev) / len(dev)),
            "fraction_within_tolerance": sum(1 for d in dev if abs(d) <= tol) / len(dev), "peak_roll_force_kn": max(peaks),
            "target_mm": target}
