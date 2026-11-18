#!/usr/bin/env python3
"""Author data/benchmark_problems/benchmarks.json (7 positive pairs with negative lookalikes).

Each query is an independently written structured problem. `acceptable` lists seed systems a human would call a
fair structural analog (the first is the primary target). `lookalikes` are hand written entries that reuse the
query vocabulary (same words, same roles) but have a different structure. In addition the evaluation script builds
a rewired control for every positive (same nodes and roles, edges re-wired) so structure alone is tested.

NOTE ON TUNING/EVAL OVERLAP: the author of these benchmarks also wrote the matcher. See docs/benchmark-notes.md.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_seed_data import parse_system  # noqa: E402


def query(id, title, domain, statement, goal, nodes, edges, cons, acceptable, note):
    s = parse_system(dict(id=id, name=title, domain=domain, summary=statement, nodes=nodes, edges=edges, beh="regulate",
                          dyn="delay", cons=[], refs="ogata"))
    return {"id": id, "title": title, "domain": domain, "statement": statement, "goal": goal, "graph": s["graph"],
            "constraints": [{"id": f"c{i}", "description": d, "kind": k, "expression": None, "provenance": "user", "tags": []}
                            for i, (k, d) in enumerate(cons, 1)],
            "acceptable": acceptable, "note": note}


def lookalike(id, name, domain, summary, nodes, edges):
    s = parse_system(dict(id=id, name=name, domain=domain, summary=summary, nodes=nodes, edges=edges, beh="regulate",
                          dyn="delay", cons=[("hard", "Placeholder lookalike constraint", "hard_limit")], refs="ogata", conf="low",
                          lim="Synthetic benchmark lookalike, not a real catalogued system."))
    s["behaviours"], s["dynamics"], s["constraints"] = [], [], []
    s["sources"] = [{"citation": "synthetic benchmark control, not a real system", "kind": "synthetic", "note": ""}]
    return s


PAIRS = [
 dict(query=query("bq_datacenter_cooling", "Data center cooling loop", "mechanical_engineering",
   "Servers produce heat. Temperature sensors report to a controller that drives fans to remove heat to the outside air, "
   "keeping temperature regulated near a set point despite changing load. Fans have limited capacity and temperature must not exceed a safe limit.",
   "Keep temperature near the set point and avoid overheating",
   "servers:Servers:producer;heat:Room temperature:medium;sensor:Temperature sensors:sensor;ctrl:Cooling controller:controller;fans:Fans:actuator;outside:Outside air:sink",
   "servers>produces>heat;heat>observed_by>sensor;sensor>signals>ctrl;ctrl>activates>fans;fans>inhibits>heat;fans>dissipates_to>outside",
   [("hard", "Temperature must not exceed a safe limit; fan capacity is a maximum")], ["bio_thermoregulation", "me_room_thermostat"], "negative feedback loop with sensor, controller, actuator"),
  positive="bio_thermoregulation",
  lookalikes=[lookalike("la_datacenter_open_loop", "Data center cooling with timer fans", "mechanical_engineering",
   "Servers produce heat. Temperature sensors show readings on a display. A timer controller runs fans to move heat to the outside air on a fixed schedule.",
   "servers:Servers:producer;heat:Room temperature:medium;sensor:Temperature sensors:sensor;display:Wall display:sink;ctrl:Fan timer controller:controller;fans:Fans:actuator;outside:Outside air:sink",
   "servers>produces>heat;heat>observed_by>sensor;sensor>signals>display;ctrl>activates>fans;fans>dissipates_to>outside")]),
 dict(query=query("bq_router_bottleneck", "Router buffer at a bottleneck link", "computer_science",
   "Senders push packets over an upstream link into a bottleneck link. When demand exceeds capacity a queue builds in a buffer and spills back, "
   "reducing upstream throughput. Link capacity is a maximum and the queue grows while demand is high.",
   "Understand queue buildup and throughput limits",
   "senders:Senders:source;upstream:Upstream link:conduit;bottleneck:Bottleneck link:regulator;downstream:Downstream link:conduit;receiver:Receiver:sink;buffer:Packet buffer:buffer",
   "senders>flows_to>upstream;upstream>flows_to>bottleneck;bottleneck>flows_to>downstream;downstream>flows_to>receiver;upstream>stores_in>buffer;buffer>constrains>upstream",
   [("hard", "Link capacity is a maximum throughput")], ["trans_highway_bottleneck"], "queue with spillback at a capacity limited section"),
  positive="trans_highway_bottleneck",
  lookalikes=[lookalike("la_router_star", "Router buffers on a star network", "computer_science",
   "Senders push packets over links through a bottleneck link into a packet buffer. Receivers read the buffer. Queue and buffer sizes are configured per link.",
   "senders:Senders:source;upstream:Upstream link:conduit;bottleneck:Bottleneck link:regulator;buffer:Packet buffer:buffer;receiver:Receiver:sink;monitor:Link monitor:sensor",
   "senders>flows_to>upstream;senders>flows_to>bottleneck;buffer>flows_to>receiver;monitor>observed_by>buffer;receiver>flows_to>upstream")]),
 dict(query=query("bq_autocatalytic_pair", "Autocatalytic species with a consuming partner", "chemistry",
   "Species X reinforces its own production and also drives formation of species Y. Y consumes X and decays, so X and Y rise and fall in coupled cycles. "
   "Concentrations are non-negative and the cycle repeats with a delay.",
   "Explain sustained oscillation", "x:Species X:producer;y:Species Y:consumer;decay:Decay of Y:sink",
   "x>activates>x;x>activates>y;y>consumes>x;y>dissipates_to>decay",
   [("hard", "Concentrations cannot be negative")], ["eco_predator_prey", "chem_oregonator"], "coupled self-reinforcing producer and consumer"),
  positive="eco_predator_prey",
  lookalikes=[lookalike("la_autocatalytic_chain", "Sequential reaction chain of species X and Y", "chemistry",
   "Species X is produced, converted to species Y, and Y decays. Concentrations of X and Y are tracked as they rise and fall in a cycle of batches.",
   "x:Species X:producer;y:Species Y:consumer;decay:Decay of Y:sink;feed:Batch feed:source",
   "feed>flows_to>x;x>flows_to>y;y>dissipates_to>decay")]),
 dict(query=query("bq_pipe_split", "Parallel water pipes between manifold and header", "architecture",
   "A pump feeds a manifold where flow splits into two parallel pipes and recombines at a header before reaching the drain. "
   "Flow into a node equals flow out and each pipe has a capacity limit.",
   "Estimate how flow shares between pipes", "pump:Pump:source;manifold:Supply manifold:junction;pipea:Pipe A:conduit;pipeb:Pipe B:conduit;header:Header:junction;drain:Drain:sink",
   "pump>flows_to>manifold;manifold>flows_to>pipea;manifold>flows_to>pipeb;pipea>flows_to>header;pipeb>flows_to>header;header>flows_to>drain",
   [("hard", "Flow is conserved at nodes; each pipe has a capacity limit")], ["phys_resistor_network", "math_max_flow_network"], "series-parallel split and recombination"),
  positive="phys_resistor_network",
  lookalikes=[lookalike("la_pipe_series", "Pump, manifold and pipes in series", "architecture",
   "A pump feeds a manifold, through pipe A then pipe B in series to a header and the drain. Manifold, pipes and header are sized for flow.",
   "pump:Pump:source;manifold:Supply manifold:junction;pipea:Pipe A:conduit;pipeb:Pipe B:conduit;header:Header:junction;drain:Drain:sink",
   "pump>flows_to>manifold;manifold>flows_to>pipea;pipea>flows_to>pipeb;pipeb>flows_to>header;header>flows_to>drain")]),
 dict(query=query("bq_flour_stock", "Bakery flour stock with a full-level counter", "logistics",
   "A supplier delivers flour through an ordering gate into stock. Bakers consume flour. A stock counter signals the gate to stop deliveries when stock is full, "
   "keeping the stock level regulated. Storage capacity is a maximum.",
   "Keep stock level near full without overflow", "supplier:Supplier:source;gate:Ordering gate:regulator;stock:Flour stock:buffer;bakers:Bakers:consumer;counter:Stock counter:sensor",
   "supplier>flows_to>gate;gate>flows_to>stock;stock>flows_to>bakers;stock>observed_by>counter;counter>inhibits>gate",
   [("hard", "Storage capacity is a maximum")], ["me_float_valve_cistern", "log_reorder_point_inventory"], "buffer level sensed to close its own inflow"),
  positive="me_float_valve_cistern",
  lookalikes=[lookalike("la_flour_counter_report", "Bakery flour stock with a weekly report", "logistics",
   "A supplier delivers flour through an ordering gate into stock. Bakers consume flour. A stock counter reports the stock level to a weekly report. Storage capacity is a maximum.",
   "supplier:Supplier:source;gate:Ordering gate:regulator;stock:Flour stock:buffer;bakers:Bakers:consumer;counter:Stock counter:sensor;report:Weekly report:sink",
   "supplier>flows_to>gate;gate>flows_to>stock;stock>flows_to>bakers;stock>observed_by>counter;counter>signals>report")]),
 dict(query=query("bq_vehicle_suspension", "Vehicle suspension over a bump", "mechanical_engineering",
   "A road bump applies a force to the sprung mass. The spring pushes back and the shock absorber damps the motion, dissipating energy as heat, "
   "so the body oscillates and settles. Energy is conserved and spring travel is limited.",
   "Choose damping so the motion settles quickly", "bump:Road bump:source;mass:Sprung mass:buffer;spring:Coil spring:buffer;shock:Shock absorber:dissipater;heat:Heat to air:sink",
   "bump>flows_to>mass;mass>activates>spring;spring>inhibits>mass;mass>activates>shock;shock>inhibits>mass;shock>dissipates_to>heat",
   [("hard", "Energy is conserved; spring travel is a hard limit")], ["phys_rlc_circuit", "phys_mass_spring_damper"], "second order oscillator with damping"),
  positive="phys_rlc_circuit",
  lookalikes=[lookalike("la_suspension_chain", "Vehicle suspension parts list over a bump", "mechanical_engineering",
   "A road bump applies a force to the sprung mass. The mass carries a coil spring and a shock absorber that sheds heat to the air. Spring and shock are fixed in series with the frame.",
   "bump:Road bump:source;mass:Sprung mass:buffer;spring:Coil spring:buffer;shock:Shock absorber:dissipater;heat:Heat to air:sink",
   "bump>flows_to>mass;mass>flows_to>spring;spring>flows_to>shock;shock>dissipates_to>heat")]),
 dict(query=query("bq_gauge_control", "Strip gauge control with a measuring gauge", "mechanical_engineering",
   "A thickness gauge measures the exit strip and signals a controller that adjusts the screwdown, which sets the roll gap that constrains the rolls, "
   "so thickness variation is regulated. The roll force must not exceed a limit and the loop has delay.",
   "Hold exit thickness within tolerance", "rolls:Rolls:transformer;strip:Exit strip:medium;gauge:Thickness gauge:sensor;ctrl:Gauge controller:controller;screwdown:Screwdown:actuator;gap:Roll gap:regulator",
   "rolls>converts>strip;strip>observed_by>gauge;gauge>signals>ctrl;ctrl>controls>screwdown;screwdown>controls>gap;gap>constrains>rolls",
   [("hard", "Roll force must not exceed a limit; loop delay limits stability")], ["econ_taylor_rule", "trans_ramp_metering"], "sensor-controller-actuator loop around a process"),
  positive="econ_taylor_rule",
  lookalikes=[lookalike("la_gauge_scrambled", "Strip gauge control parts list", "mechanical_engineering",
   "A thickness gauge, a controller, a screwdown and a roll gap act on the rolls and the exit strip. The controller is wired to the gauge, the gauge to the screwdown, and the roll gap feeds the controller.",
   "rolls:Rolls:transformer;strip:Exit strip:medium;gauge:Thickness gauge:sensor;ctrl:Gauge controller:controller;screwdown:Screwdown:actuator;gap:Roll gap:regulator",
   "rolls>converts>strip;ctrl>controls>gauge;gauge>observed_by>screwdown;screwdown>flows_to>strip;gap>flows_to>ctrl")]),
]


def main():
    # Fairness: lookalikes claim the SAME declared behaviours, dynamics and constraint tags as the positive target,
    # so they are not penalised for missing metadata. Only structure (and wording) can separate them.
    from seed_systems_a import SYSTEMS_A
    from seed_systems_b import SYSTEMS_B
    seed = {s["id"]: parse_system(s) for s in SYSTEMS_A + SYSTEMS_B}
    for p in PAIRS:
        pos = seed[p["positive"]]
        for la in p["lookalikes"]:
            la["behaviours"], la["dynamics"] = list(pos["behaviours"]), list(pos["dynamics"])
            la["constraints"] = [dict(c, id=c["id"]) for c in pos["constraints"]]
    doc = {"description": "Positive structural analog pairs and negative lookalikes. See docs/benchmark-notes.md for caveats.",
           "split": "tuning",
           "split_note": "Seen during matcher development. The held-out set is heldout_labels.json.",
           "pairs": [{"query": p["query"], "positive": p["positive"], "lookalikes": p["lookalikes"]} for p in PAIRS]}
    path = os.path.join(ROOT, "data", "benchmark_problems", "benchmarks.json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(f"wrote {len(PAIRS)} pairs")


if __name__ == "__main__":
    main()
