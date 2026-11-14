"""Graph analytics on the typed directed multigraph (stdlib only)."""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from ..schemas import Graph


def degrees(g: Graph) -> Dict[str, Dict[str, int]]:
    d = {n.id: {"in": 0, "out": 0, "total": 0} for n in g.nodes}
    for e in g.edges:
        if e.source in d and e.target in d:
            d[e.source]["out"] += 1
            d[e.target]["in"] += 1
    for v in d.values():
        v["total"] = v["in"] + v["out"]
    return d


def adjacency(g: Graph) -> Dict[str, List[str]]:
    adj = {n.id: [] for n in g.nodes}
    for e in g.edges:
        if e.source in adj and e.target in adj:
            adj[e.source].append(e.target)
    return adj


def weakly_connected_components(g: Graph) -> List[List[str]]:
    und = {n.id: set() for n in g.nodes}
    for e in g.edges:
        if e.source in und and e.target in und:
            und[e.source].add(e.target)
            und[e.target].add(e.source)
    seen, comps = set(), []
    for n in g.nodes:
        if n.id in seen:
            continue
        comp, stack = [], [n.id]
        seen.add(n.id)
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in sorted(und[x]):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        comps.append(sorted(comp))
    return comps


def strongly_connected_components(g: Graph) -> List[List[str]]:
    """Iterative Tarjan."""
    adj = adjacency(g)
    index, low, on, stack, out = {}, {}, set(), [], []
    counter = 0
    for root in [n.id for n in g.nodes]:
        if root in index:
            continue
        work = [(root, iter(adj[root]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(adj[w])))
                    advanced = True
                    break
                elif w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(sorted(comp))
    return sorted(out)


def find_cycles(g: Graph, max_len: int = 8, limit: int = 200) -> List[List[str]]:
    """Simple cycles (as node-id lists) up to max_len, deterministic order.

    Each cycle is reported once, rooted at its smallest node id. Parallel edges
    are collapsed (use feedback_loops for edge-level polarity).
    """
    adj = {k: sorted(set(v)) for k, v in adjacency(g).items()}
    order = sorted(adj)
    cycles: List[List[str]] = []
    for start in order:
        stack = [(start, [start])]
        while stack and len(cycles) < limit:
            v, path = stack.pop()
            for w in reversed(adj[v]):
                if w == start:
                    cycles.append(list(path))
                elif w > start and w not in path and len(path) < max_len:
                    stack.append((w, path + [w]))
    cycles.sort(key=lambda c: (len(c), c))
    return cycles[:limit]


def feedback_loops(g: Graph, max_len: int = 8, limit: int = 200) -> List[dict]:
    """Cycles with polarity from edge relation signs (product of signs).

    negative product -> 'negative' (balancing), positive -> 'positive' (reinforcing).
    Uses the first edge between consecutive nodes; multi-edges with different
    signs make the loop sign ambiguous and are flagged.
    """
    by_pair: Dict[Tuple[str, str], List[int]] = {}
    for e in g.edges:
        by_pair.setdefault((e.source, e.target), []).append(e.sign)
    loops = []
    for c in find_cycles(g, max_len, limit):
        sign, ambiguous = 1, False
        for i, a in enumerate(c):
            b = c[(i + 1) % len(c)]
            signs = by_pair[(a, b)]
            if len(set(signs)) > 1:
                ambiguous = True
            sign *= signs[0]
        loops.append({"nodes": c, "length": len(c),
                      "polarity": "negative" if sign < 0 else "positive", "ambiguous": ambiguous})
    return loops


def bfs_distances(adj: Dict[str, List[str]], s: str) -> Dict[str, int]:
    dist = {s: 0}
    q = deque([s])
    while q:
        v = q.popleft()
        for w in adj[v]:
            if w not in dist:
                dist[w] = dist[v] + 1
                q.append(w)
    return dist


def betweenness_centrality(g: Graph, normalized: bool = True) -> Dict[str, float]:
    """Brandes algorithm for unweighted directed graphs."""
    adj = {k: sorted(set(v)) for k, v in adjacency(g).items()}
    cb = {v: 0.0 for v in adj}
    for s in adj:
        stack, pred = [], {v: [] for v in adj}
        sigma = {v: 0 for v in adj}
        sigma[s] = 1
        dist = {v: -1 for v in adj}
        dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {v: 0.0 for v in adj}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    n = len(adj)
    if normalized and n > 2:
        scale = 1.0 / ((n - 1) * (n - 2))
        cb = {k: v * scale for k, v in cb.items()}
    return cb


def closeness_centrality(g: Graph) -> Dict[str, float]:
    adj = adjacency(g)
    n = len(adj)
    out = {}
    for v in adj:
        d = bfs_distances(adj, v)
        tot = sum(d.values())
        reach = len(d) - 1
        out[v] = (reach / tot) * (reach / (n - 1)) if tot > 0 and n > 1 else 0.0
    return out


def pagerank(g: Graph, damping: float = 0.85, iters: int = 100, tol: float = 1e-10) -> Dict[str, float]:
    adj = adjacency(g)
    n = len(adj)
    if n == 0:
        return {}
    pr = {v: 1.0 / n for v in adj}
    for _ in range(iters):
        new = {v: (1 - damping) / n for v in adj}
        dangling = sum(pr[v] for v in adj if not adj[v])
        for v in adj:
            if adj[v]:
                share = damping * pr[v] / len(adj[v])
                for w in adj[v]:
                    new[w] += share
            new[v] += damping * dangling / n
        if sum(abs(new[v] - pr[v]) for v in adj) < tol:
            pr = new
            break
        pr = new
    return pr


def depth(g: Graph) -> int:
    """Length (edges) of the longest path in the condensation DAG, starting anywhere."""
    comps = strongly_connected_components(g)
    if not comps:
        return 0
    cid = {v: i for i, c in enumerate(comps) for v in c}
    dag: Dict[int, set] = {i: set() for i in range(len(comps))}
    for e in g.edges:
        a, b = cid.get(e.source), cid.get(e.target)
        if a is not None and b is not None and a != b:
            dag[a].add(b)
    memo: Dict[int, int] = {}

    def longest(i: int) -> int:
        if i in memo:
            return memo[i]
        memo[i] = 0
        memo[i] = max([1 + longest(j) for j in dag[i]] or [0])
        return memo[i]

    return max(longest(i) for i in dag)


def max_flow(g: Graph, source: str, sink: str, capacity: Optional[Dict[str, float]] = None):
    """Edmonds-Karp on edge weights (or capacity[edge_id]). Returns (value, flow_by_edge_id)."""
    if source == sink:
        raise ValueError("source and sink must differ")
    ids = set(g.node_ids())
    if source not in ids or sink not in ids:
        raise ValueError("unknown source or sink")
    cap: Dict[Tuple[str, str], float] = {}
    edge_pair: Dict[str, Tuple[str, str]] = {}
    for e in g.edges:
        if e.source == e.target:
            continue
        c = capacity.get(e.id, e.weight) if capacity else e.weight
        cap[(e.source, e.target)] = cap.get((e.source, e.target), 0.0) + c
        cap.setdefault((e.target, e.source), 0.0)
        edge_pair[e.id] = (e.source, e.target)
    nbr: Dict[str, List[str]] = {i: [] for i in ids}
    for (a, b) in cap:
        nbr[a].append(b)
    for k in nbr:
        nbr[k].sort()
    orig = dict(cap)
    total = 0.0
    while True:
        parent = {source: None}
        q = deque([source])
        while q and sink not in parent:
            v = q.popleft()
            for w in nbr[v]:
                if w not in parent and cap[(v, w)] > 1e-12:
                    parent[w] = v
                    q.append(w)
        if sink not in parent:
            break
        b, w = float("inf"), sink
        while parent[w] is not None:
            b = min(b, cap[(parent[w], w)])
            w = parent[w]
        w = sink
        while parent[w] is not None:
            cap[(parent[w], w)] -= b
            cap[(w, parent[w])] += b
            w = parent[w]
        total += b
    pair_flow = {p: max(0.0, orig[p] - cap[p]) for p in orig}
    flow: Dict[str, float] = {}
    for eid, p in edge_pair.items():
        share = [e for e in g.edges if (e.source, e.target) == p]
        tot_w = sum((capacity.get(e.id, e.weight) if capacity else e.weight) for e in share) or 1.0
        e_obj = next(e for e in g.edges if e.id == eid)
        w_e = capacity.get(eid, e_obj.weight) if capacity else e_obj.weight
        flow[eid] = pair_flow[p] * w_e / tot_w
    return total, flow


def motifs(g: Graph) -> Dict[str, int]:
    """Counts of small structural motifs (on collapsed simple digraph)."""
    adj = {k: set(v) for k, v in adjacency(g).items()}
    for k in adj:
        adj[k].discard(k)
    nodes = sorted(adj)
    ff = 0  # feed-forward loop a->b, b->c, a->c
    chain = 0  # a->b->c with a!=c
    fan_out = fan_in = bi_fan = mutual = 0
    pred = {k: set() for k in adj}
    for a in adj:
        for b in adj[a]:
            pred[b].add(a)
    for a in nodes:
        for b in adj[a]:
            if a in adj[b] and a < b:
                mutual += 1
            for c in adj[b]:
                if c != a:
                    chain += 1
                    if c in adj[a]:
                        ff += 1
    for a in nodes:
        if len(adj[a]) >= 2:
            fan_out += 1
        if len(pred[a]) >= 2:
            fan_in += 1
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            common = adj[a] & adj[b]
            if len(common) >= 2 and b not in adj[a] and a not in adj[b]:
                bi_fan += 1
    self_loops = sum(1 for e in g.edges if e.source == e.target)
    return {"feed_forward_loop": ff, "chain3": chain, "fan_out": fan_out, "fan_in": fan_in,
            "bi_fan": bi_fan, "mutual_pair": mutual, "self_loop": self_loops}


def metrics(g: Graph) -> dict:
    n, m = len(g.nodes), len(g.edges)
    deg = degrees(g)
    comps = weakly_connected_components(g)
    sccs = strongly_connected_components(g)
    loops = feedback_loops(g)
    possible = n * (n - 1)
    simple_edges = {(e.source, e.target) for e in g.edges if e.source != e.target}
    bc = betweenness_centrality(g)
    out_deg = [v["out"] for v in deg.values()]
    in_deg = [v["in"] for v in deg.values()]
    return {
        "node_count": n, "edge_count": m,
        "density": (len(simple_edges) / possible) if possible else 0.0,
        "mean_degree": (2.0 * m / n) if n else 0.0,
        "max_out_degree": max(out_deg or [0]), "max_in_degree": max(in_deg or [0]),
        "components": len(comps),
        "cyclic_components": sum(1 for c in sccs if len(c) > 1 or
                                 any(e.source == e.target == c[0] for e in g.edges)),
        "cycle_count": len(loops),
        "negative_loops": sum(1 for l in loops if l["polarity"] == "negative"),
        "positive_loops": sum(1 for l in loops if l["polarity"] == "positive"),
        "depth": depth(g),
        "max_betweenness": max(bc.values()) if bc else 0.0,
        "motifs": motifs(g),
    }
