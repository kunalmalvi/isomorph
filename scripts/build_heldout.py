#!/usr/bin/env python3
"""Author data/benchmark_problems/heldout_labels.json and review_template.json.

HELD-OUT SET. 20 queries, graded labels (2 strong, 1 partial, 0 not analog) written from docs/labelling-guide.md.
The labels in this file were written WITHOUT running the matcher on these queries. They are `author_labelled`
and `independent_review: none`. The author of the labels also wrote the matcher, so the held-out set is only less
overlapping with the tuning set, it is not independent. Do not edit labels after the first evaluation run except
through a logged amendment in docs/benchmark-notes.md.

Candidate ids must exist in data/seed_knowledge or data/mechanisms (checked at build time, no matcher involved).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_benchmarks import query  # noqa: E402


def L(system_id, grade, mapping, rationale, lookalike=None):
    """mapping: 'query_node:system_node,...' or '' for none. lookalike: reason string or None."""
    rm = dict(p.split(":") for p in mapping.split(",")) if mapping else {}
    d = {"system_id": system_id, "grade": grade, "rationale": rationale, "role_mapping": rm,
         "lookalike": lookalike is not None, "label_status": "author_labelled", "independent_review": "none"}
    if lookalike is not None:
        d["lookalike_reason"] = lookalike
    return d


Q = []


def add(q, labels):
    Q.append((q, labels))


add(query("hq_sauna_stove", "Sauna stove with a limit controller", "mechanical_engineering",
  "A wood stove heats the sauna air. A probe measures the air temperature and tells a limit controller, which dampens the stove "
  "when the air is too hot. Some heat leaves through the roof vent. The stove has a maximum output.",
  "Hold the sauna air near a target temperature",
  "wood:Firewood:source;stove:Stove:actuator;air:Sauna air:medium;probe:Temperature probe:sensor;ctl:Limit controller:controller;vent:Roof vent:sink",
  "wood>flows_to>stove;stove>produces>air;air>observed_by>probe;probe>signals>ctl;ctl>inhibits>stove;air>dissipates_to>vent",
  [("hard", "Stove output has a maximum")], [], "negative feedback with a loss path"), [
  L("me_room_thermostat", 2, "wood:supply,stove:heater,air:room,probe:sensor,ctl:thermostat,vent:loss",
    "Fuel to supply, stove to heater, air to room, probe to sensor, limit controller to thermostat, vent to loss. Sensed temperature inhibits the heater in both and heat escapes to a loss node, so the loop and dynamics correspond."),
  L("bio_thermoregulation", 1, "stove:heat_prod,air:core_temp,probe:thermoreceptor,ctl:hypothalamus,vent:environment",
    "The sensor to controller loop on a regulated temperature maps. In the candidate the controller drives a separate cooling actuator, in the query it dampens the heat source itself, so the edge from controller to actuator differs."),
  L("cs_circuit_breaker", 1, "stove:service,probe:monitor",
    "Only the monitor-inhibits-the-protected-element fragment maps. There is no regulated medium and no loss path."),
  L("arch_stack_ventilation", 0, "", "The candidate has a room, a vent and a heat gain, but no sensor or controller. Airflow is driven by buoyancy, not by a sensed signal, so check 3 fails.",
    "shares the words room, vent, heat gain with the query but has no sensing loop"),
  L("math_mm1_queue", 0, "", "Series queue with no feedback. No regulated quantity, check 3 fails.")])

add(query("hq_canal_intake", "Canal intake gate and reservoir gauge", "architecture",
  "A river feeds a reservoir through an intake gate. A gauge reports the reservoir level to an operator who closes the gate when the level is high. "
  "The town draws water from the reservoir. The reservoir has a maximum volume.",
  "Keep the reservoir below the brim without running dry",
  "river:River:source;gate:Intake gate:actuator;reservoir:Reservoir:buffer;gauge:Level gauge:sensor;operator:Operator:controller;town:Town:consumer",
  "river>flows_to>gate;gate>flows_to>reservoir;reservoir>flows_to>town;reservoir>observed_by>gauge;gauge>signals>operator;operator>inhibits>gate",
  [("hard", "Reservoir volume has a maximum")], [], "buffer level sensed to close its own inflow"), [
  L("log_reorder_point_inventory", 2, "river:supplier,gate:pipeline,reservoir:stock,gauge:counter,operator:policy,town:customers",
    "Supplier to river, pipeline to gate, stock to reservoir, counter to gauge, policy to operator, customers to town. The sensed level signals a controller that inhibits the inflow, as in the query."),
  L("me_float_valve_cistern", 1, "river:mains,gate:inlet,reservoir:tank,gauge:float,town:outlet",
    "Level closes its own inlet and the buffer drains to a consumer. The candidate has no separate controller node, so gauge and operator collapse into the float, which is why this is partial."),
  L("cs_bounded_buffer", 1, "river:producer,reservoir:buffer,town:consumer,operator:semaphore",
    "A full buffer signals a regulator that blocks the producer. No separate sensor node and the regulator also blocks the consumer, which the query does not do."),
  L("arch_roof_drainage", 1, "river:rain,reservoir:gutter,gate:overflow,town:drain",
    "Level in a buffer triggers a relief path. The relief acts on the outflow, not on the inflow, so only part of the loop corresponds."),
  L("log_cross_docking", 0, "", "Straight-through flow with a staging buffer and no sensing loop, check 3 fails.",
    "shares the words buffer, inbound and outbound flows with the query but has no sensing loop")])

add(query("hq_greenhouse_irrigation", "Greenhouse soil moisture irrigation", "ecology",
  "Mains water passes an irrigation valve into the soil. A moisture probe tells an irrigation controller which opens or closes the valve. "
  "Extra water drains away. Valve flow has a maximum.",
  "Hold soil moisture near a target",
  "mains:Mains water:source;valve:Irrigation valve:actuator;soil:Soil:medium;probe:Moisture probe:sensor;ctl:Irrigation controller:controller;drain:Drainage:sink",
  "mains>flows_to>valve;valve>flows_to>soil;soil>observed_by>probe;probe>signals>ctl;ctl>controls>valve;soil>flows_to>drain",
  [("hard", "Valve flow has a maximum")], [], "sensed medium, controller, valve, drain"), [
  L("arch_vav_zone_control", 2, "mains:supply_duct,valve:damper,soil:zone,probe:thermostat,ctl:controller,drain:exhaust",
    "All six nodes and all six edges correspond one to one: supply, actuator, controlled medium, sensor, controller, exhaust."),
  L("arch_daylight_shading_control", 1, "mains:sun,valve:blinds,soil:room,probe:sensor,ctl:controller",
    "The sensed medium, controller and actuator loop maps, but the candidate has no exit path from the medium, so the medium is not drained."),
  L("econ_taylor_rule", 1, "soil:inflation,probe:statistics,ctl:bank,valve:rate",
    "Sensor to controller to actuator acting back on a medium maps. The candidate has no source or sink and the loop closes through a consumer, so only the loop maps."),
  L("arch_roof_drainage", 0, "", "Water enters, is buffered and drains, but there is no sensor or controller. Overflow is passive, check 3 fails.",
    "shares water, drain and valve-like words with the query but is passive"),
  L("energy_thermal_storage_tank", 0, "", "Source to buffer to consumer with a loss and no feedback.")])

add(query("hq_pressure_cooker", "Pressure cooker with weighted lid", "physics",
  "A stove heats water and produces steam pressure. When pressure exceeds what the lid weight holds, the lid lifts and lets steam out to the vent, "
  "which lowers the pressure. The weight sets the lifting pressure.",
  "Hold pressure at a safe level",
  "stove:Stove:source;steam:Steam pressure:medium;lid:Lid:switch;weight:Lid weight:regulator;vent:Vent:sink",
  "stove>produces>steam;steam>activates>lid;weight>inhibits>lid;lid>flows_to>vent;lid>inhibits>steam",
  [("hard", "Pressure must not exceed a safe limit")], [], "threshold relief"), [
  L("me_pressure_relief_valve", 2, "stove:process,steam:pressure,lid:valve,weight:spring,vent:vent",
    "Every node and edge corresponds: pressure activates the valve against a spring-like regulator, the valve vents and lowers the pressure."),
  L("me_hydraulic_press", 1, "steam:fluid,lid:relief,vent:reservoir",
    "A relief element that passes fluid to a reservoir when pressure is high maps. The candidate also has a pump and a ram, which the query lacks, and the relief does not act back on the fluid edge."),
  L("arch_roof_drainage", 1, "steam:gutter,lid:overflow,vent:drain",
    "A buffer or medium level triggers a relief path to a sink. No weight or threshold regulator and no inhibition back onto the medium."),
  L("chem_distillation_column", 0, "", "Heat input, vapour, and outlets, but no relief switch and no feedback onto the vapour. Flows only.",
    "shares the words heat, vapour, vent-like outlets with the query")])

add(query("hq_emergency_ward", "Emergency ward patient queue", "logistics",
  "Patients arrive at the ward and wait in the waiting room until a doctor is free. Doctors treat one patient at a time and then discharge them. "
  "The waiting room grows when arrivals exceed the treatment rate.",
  "Estimate waiting room length",
  "arrivals:Arriving patients:source;waiting:Waiting room:buffer;doctors:Doctors:transformer;discharge:Discharged:sink",
  "arrivals>flows_to>waiting;waiting>flows_to>doctors;doctors>flows_to>discharge",
  [("hard", "Treatment rate is a maximum")], [], "single server queue"), [
  L("math_mm1_queue", 2, "arrivals:arrivals,waiting:queue,doctors:server,discharge:departures",
    "Four nodes and three edges correspond one to one. Both grow a queue when arrivals exceed service."),
  L("cs_cpu_scheduler", 1, "arrivals:processes,waiting:ready,doctors:cpu,discharge:done",
    "The ready queue feeding a single server maps. The candidate adds a dispatcher and a return edge from cpu to the queue that the query does not have."),
  L("trans_airport_runway", 1, "arrivals:arrivals,waiting:holding,doctors:runway,discharge:gate",
    "Arrivals queue then single server then exit maps. The air traffic controller loop has no counterpart in the query."),
  L("trans_signal_cycle_queue", 1, "arrivals:arrivals,waiting:queue,doctors:stopline,discharge:downstream",
    "Queue to a gated server to downstream maps. The signal switch that gates service has no counterpart."),
  L("trans_bus_bunching", 0, "", "Waiting is activated by headway and feeds back to itself. This is a reinforcing loop, not a plain queue, check 3 fails.",
    "shares the words waiting and passengers or arrivals with the query but loops back")])

add(query("hq_port_crane_bottleneck", "Container port crane bottleneck", "logistics",
  "Ships arrive through an approach channel to a crane berth. The berth works slower than ships arrive, so ships queue at the anchorage and block the channel. "
  "Containers then move over the yard to trucks. Berth capacity is a maximum.",
  "Understand why ships queue at the anchorage",
  "ships:Arriving ships:source;approach:Approach channel:conduit;crane:Crane berth:regulator;yard:Container yard:conduit;trucks:Trucks:sink;anchorage:Anchorage:buffer",
  "ships>flows_to>approach;approach>flows_to>crane;crane>flows_to>yard;yard>flows_to>trucks;approach>stores_in>anchorage;anchorage>constrains>approach",
  [("hard", "Berth capacity is a maximum throughput")], [], "queue with spillback at a capacity limited section"), [
  L("trans_highway_bottleneck", 2, "ships:demand,approach:upstream,crane:bottleneck,yard:downstream,trucks:exit,anchorage:queue",
    "All six nodes and six edges correspond. The queue stores overflow from the upstream section and constrains it, as in the query."),
  L("log_theory_of_constraints", 1, "ships:release,crane:bottleneck,anchorage:buffer,trucks:market",
    "A bottleneck stage with an upstream buffer and a constraint on release maps. The candidate has the constraint on the release rate, not a spillback from the buffer to the upstream conduit."),
  L("trans_toll_plaza_queue", 1, "ships:highway,crane:booth,anchorage:queue,trucks:exit",
    "A queue ahead of a limited server maps. The queue inhibits the source in the candidate rather than constraining the upstream conduit."),
  L("log_hub_and_spoke", 0, "", "Merging flows through a trunk, no buffer and no capacity spillback. Check 3 fails.",
    "shares conduit, sink and source types and the words channel or trunk with the query but has no buffer")])

add(query("hq_playground_swing", "Playground swing with air drag", "physics",
  "A push gives the swing seat energy. The seat swings, the rope tension pulls it back, and air drag dissipates energy as heat, so the swing slowly stops. "
  "Rope length limits the swing angle.",
  "Predict how quickly the swing stops",
  "push:Push:source;seat:Swing seat:buffer;rope:Rope tension:buffer;drag:Air drag:dissipater;heat:Warmed air:sink",
  "push>flows_to>seat;seat>activates>rope;rope>inhibits>seat;seat>activates>drag;drag>inhibits>seat;drag>dissipates_to>heat",
  [("hard", "Rope length limits the swing angle")], [], "damped second order oscillator"), [
  L("phys_mass_spring_damper", 2, "push:force,seat:mass,rope:spring,drag:damper,heat:heat",
    "Every node and edge corresponds: exchange between two stores and a dissipater that inhibits the first store."),
  L("phys_rlc_circuit", 2, "push:vsource,seat:inductor,rope:capacitor,drag:resistor,heat:heat",
    "Same wiring, store to store exchange with a dissipater, giving damped oscillation."),
  L("me_tuned_mass_absorber", 1, "seat:main,rope:absorber,drag:damper",
    "A second store coupled to a main mass and a dissipater maps, but the coupling and the source differ."),
  L("phys_clock_escapement", 1, "push:drive,seat:pendulum,drag:friction",
    "A pendulum with friction fed by a drive maps. The escapement switch is not in the query and the oscillator has one store only."),
  L("me_flywheel", 0, "", "Energy buffer with a loss, no exchange between two stores, no oscillation. Check 3 fails.",
    "shares the words energy, drag-like loss and buffer with the query but has no second store or inhibition loop")])

add(query("hq_hog_cycle", "Hog price cycle", "economics",
  "A high pork price makes farmers raise more hogs. The herd takes time to grow, then supplies shoppers. A large herd lowers the price. "
  "The delay makes price and herd size rise and fall in cycles.",
  "Explain repeating price swings",
  "price:Pork price:medium;farmers:Hog farmers:producer;herd:Hog herd:buffer;shoppers:Shoppers:consumer",
  "price>activates>farmers;farmers>flows_to>herd;herd>flows_to>shoppers;herd>inhibits>price",
  [("hard", "Herd size cannot be negative")], [], "delayed price and supply feedback"), [
  L("econ_market_price_adjustment", 2, "price:price,farmers:producers,herd:inventory,shoppers:consumers",
    "Four nodes and four edges correspond. The delayed supply response and inventory pressure on price give the same cycle."),
  L("log_supply_chain_bullwhip", 1, "farmers:factory,herd:wholesaler,shoppers:retailer",
    "Delayed buffers with back edges give oscillation, but the price signal has no counterpart and the loop passes through several buffers."),
  L("bio_end_product_inhibition", 1, "price:enzyme1,farmers:pathway,herd:product,shoppers:demand",
    "A buffer that inhibits the upstream regulator while a consumer draws it down. Shared negative feedback, but no delay-driven oscillation is claimed in the candidate."),
  L("math_mm1_queue", 0, "", "Series queue with no feedback, check 3 fails."),
  L("econ_commons_depletion", 0, "", "A stock with regeneration and users. The only loop is reinforcing regeneration and competition between users, not price inhibition.",
    "shares the words stock and users or producers and an economic setting with the query")])

add(query("hq_viral_posts", "Viral posts and moderators", "computer_science",
  "Popular posts spread by themselves and also draw the attention of moderators. Moderators remove posts and then burn out and leave. "
  "As posts fall moderators have less to do and the next wave of posts can grow again.",
  "Explain repeated waves of viral content",
  "posts:Viral posts:producer;mods:Moderators:consumer;burnout:Burnout:sink",
  "posts>activates>posts;posts>activates>mods;mods>consumes>posts;mods>dissipates_to>burnout",
  [("hard", "Counts cannot be negative")], [], "self-reinforcing producer and consumer"), [
  L("eco_predator_prey", 2, "posts:prey,mods:predator,burnout:mortality",
    "Self-reinforcing prey, a predator that grows from prey and consumes it, and a loss for the predator. All four edges correspond."),
  L("chem_oregonator", 1, "posts:activator,mods:inhibitor,burnout:products",
    "Self-activation with an inhibitor that suppresses it gives oscillation, but the candidate has an extra catalyst step and a source."),
  L("chem_autocatalysis", 1, "posts:product",
    "Self-activation maps. No consumer and no limiting partner, so no oscillation."),
  L("math_markov_chain", 0, "", "Probability transfer among states, no self-reinforcement. Check 3 fails."),
  L("eco_trophic_cascade", 0, "", "A consumption chain with no self-reinforcement and no feedback on the lowest level.",
    "shares the words consumer, consumes and producer with the query but is a one-way chain")])

add(query("hq_wastewater_clarifiers", "Wastewater inflow split over two clarifiers", "architecture",
  "Wastewater enters an inlet works and reaches a distribution chamber, which splits the flow between two clarifiers. Both clarifiers discharge into one effluent channel "
  "that runs to the river. Flow into a chamber equals flow out and each clarifier has a capacity limit.",
  "Estimate how flow shares between clarifiers",
  "inlet:Inlet works:source;split:Distribution chamber:junction;clarifier_a:Clarifier A:conduit;clarifier_b:Clarifier B:conduit;channel:Effluent channel:junction;river:River:sink",
  "inlet>flows_to>split;split>flows_to>clarifier_a;split>flows_to>clarifier_b;clarifier_a>flows_to>channel;clarifier_b>flows_to>channel;channel>flows_to>river",
  [("hard", "Flow is conserved at chambers; each clarifier has a capacity limit")], [], "split into parallel branches and recombine"), [
  L("phys_resistor_network", 2, "inlet:battery,split:split,clarifier_a:r1,clarifier_b:r2,channel:join,river:ground",
    "Six nodes and six edges correspond. Conservation at a junction is Kirchhoff's current law."),
  L("math_max_flow_network", 1, "inlet:s,clarifier_a:a,clarifier_b:b,channel:m,river:t",
    "Two parallel conduits merging into a junction and a sink map. The candidate splits directly at the source and adds a cut regulator."),
  L("arch_truss_load_path", 1, "inlet:load,split:joint1,clarifier_a:chord,clarifier_b:web,river:support",
    "Split into two paths that rejoin at a sink maps, but one branch continues through an extra conduit and there is no merging junction."),
  L("trans_wardrop_equilibrium", 1, "inlet:demand,clarifier_a:route_a,clarifier_b:route_b,river:destination",
    "Two parallel routes from a source to a sink map. No distribution or merge junctions and a competition edge that the query does not have."),
  L("arch_progressive_collapse", 0, "", "Loads pass down a chain of columns, with the foundation as sink. Not a two-branch split and recombine.",
    "shares the words conduit-like parts, load and sink with the query but is a chain")])

add(query("hq_plankton_food_chain", "Antarctic plankton food chain", "ecology",
  "Sunlight feeds phytoplankton. Krill eat phytoplankton, fish eat krill, and seals eat fish. Each level is limited by what the level below supplies.",
  "Predict how removing seals affects plankton",
  "sun:Sunlight:source;plankton:Phytoplankton:producer;krill:Krill:consumer;fish:Fish:consumer;seal:Seals:consumer",
  "sun>flows_to>plankton;krill>consumes>plankton;fish>consumes>krill;seal>consumes>fish",
  [("hard", "Populations cannot be negative")], [], "consumption chain"), [
  L("eco_trophic_cascade", 2, "sun:sun,plankton:kelp,krill:urchin,fish:otter,seal:orca",
    "Five nodes and four edges correspond one to one: source, producer and a chain of three consumers."),
  L("chem_series_reaction", 1, "plankton:a,krill:b,fish:c",
    "A conversion chain maps the chain shape but replaces consumption by conversion and has no source."),
  L("phys_decay_chain", 1, "plankton:parent,krill:daughter,fish:stable",
    "A chain of three stages. Conversion, not consumption, and a decay is spontaneous."),
  L("eco_competitive_exclusion", 0, "", "Two consumers compete for one resource. Parallel competition, no chain, check 2 fails."),
  L("eco_nitrogen_cycle", 0, "", "The flow closes into a cycle through decomposers, whereas the query is an open chain.",
    "shares the words plants, source and consumers with the query but forms a closed cycle")])

add(query("hq_reef_algae_shift", "Coral reef shift to algae", "ecology",
  "Nutrient runoff enters the reef water. Nutrients let macroalgae grow, and a dense algal cover smothers coral. Healthy coral keeps algae in check, "
  "so once coral is lost the algae are hard to remove.",
  "Explain why the reef does not recover after cleanup",
  "runoff:Nutrient runoff:source;nutrients:Reef nutrients:buffer;algae:Macroalgae:producer;cover:Smothering cover:medium;coral:Coral:consumer",
  "runoff>flows_to>nutrients;nutrients>activates>algae;algae>activates>cover;cover>inhibits>coral;coral>inhibits>algae",
  [("hard", "Cover cannot exceed the reef area")], [], "regime shift through mutual inhibition"), [
  L("eco_lake_eutrophication", 2, "runoff:loading,nutrients:phosphorus,algae:algae,cover:turbidity,coral:plants",
    "Five nodes and five edges correspond. Mutual suppression between algae and the plants or coral gives a regime shift with hysteresis."),
  L("math_saddle_node_switch", 1, "nutrients:param,cover:state",
    "The shared dynamics, a threshold switch with hysteresis, correspond. The wiring differs and only the driver to state fragment maps."),
  L("econ_lemons_unraveling", 1, "algae:good,cover:quality,coral:buyers",
    "A reinforcing unravelling loop maps in outline. The edge relations differ."),
  L("eco_nitrogen_cycle", 0, "", "A nutrient cycle with no mutual inhibition and no regime shift.",
    "shares the words nutrient, soil-like buffer and plants with the query but is a transport cycle")])

add(query("hq_cruise_control", "Car cruise control", "mechanical_engineering",
  "The driver sets a speed. The controller compares it with the measured speed, and adjusts the throttle to drive the car toward that speed. A speed sensor reports the car's speed. "
  "Throttle opening has a maximum.",
  "Hold the set speed on hills",
  "driver:Speed setting:source;error:Speed error:junction;ctl:Cruise controller:controller;throttle:Throttle:actuator;car:Car:transformer;speedo:Speed sensor:sensor",
  "driver>flows_to>error;error>signals>ctl;ctl>controls>throttle;throttle>controls>car;car>observed_by>speedo;speedo>inhibits>error",
  [("hard", "Throttle opening has a maximum")], [], "set point comparison feedback"), [
  L("math_pid_control", 2, "driver:setpoint,error:sum,ctl:pid,throttle:pid,car:plant,speedo:sensor",
    "Set point to summing junction, controller, plant and a sensor that subtracts at the junction all correspond. The throttle is merged into the controller. The integral term is not needed."),
  L("phys_opamp_negative_feedback", 1, "driver:input,error:sense,throttle:amp,car:output,speedo:network",
    "A setpoint, a comparison, an amplifier and a feedback path that opposes the input map. The candidate has no explicit controller node."),
  L("me_centrifugal_governor", 1, "car:speed,speedo:flyballs,ctl:linkage,throttle:throttle",
    "Speed sensed and a linkage moves a throttle. There is no set point and the controller inhibits the throttle directly."),
  L("econ_taylor_rule", 1, "car:inflation,speedo:statistics,ctl:bank,throttle:rate",
    "Sensor to controller to actuator onto a process maps. No explicit set point comparison."),
  L("math_linear_program", 0, "", "An optimiser controls activities that compete for a resource. There is no sensed feedback, check 3 fails.",
    "shares the words controller, controls and constraints with the query but has no feedback")])

add(query("hq_line_trip_cascade", "Cascading transmission line trips", "energy_systems",
  "A storm trips line 1, so its load moves to line 2. Line 2 then overloads and its load moves to line 3, which overloads and passes load back to line 1. "
  "Each line has a capacity limit.",
  "Explain how one trip becomes a blackout",
  "storm:Storm:source;line1:Line 1:buffer;line2:Line 2:buffer;line3:Line 3:buffer",
  "storm>flows_to>line1;line1>transmits>line2;line2>transmits>line3;line3>transmits>line1",
  [("hard", "Each line has a capacity limit")], [], "contagion around a ring"), [
  L("econ_banking_contagion", 2, "storm:shock,line1:banka,line2:bankb,line3:bankc",
    "Shock, then a ring of three nodes that pass the load around. All four edges correspond."),
  L("log_supply_chain_bullwhip", 1, "storm:demand,line1:retailer,line2:wholesaler,line3:factory",
    "A chain of buffers that pass effects on, with a return edge. The candidate's return edge goes to the middle node, not the first."),
  L("math_markov_chain", 1, "line1:sa,line2:sb,line3:sc",
    "A three state loop maps. The candidate has an extra back edge and a regulator."),
  L("arch_progressive_collapse", 1, "storm:loads,line1:col_a,line2:col_b,line3:col_c",
    "Load passes along a chain of members that fail in turn. The candidate does not close into a ring."),
  L("eco_carbon_box_model", 0, "", "Three reservoirs with exchange flows around a hub, not a ring with failure propagation.",
    "shares the words three buffers, source and flows with the query but is a hub exchange")])

add(query("hq_vaccine_fridge", "Solar vaccine fridge", "energy_systems",
  "A solar charger cools a cold store. The clinic draws vaccines from the cold store, and heat leaks in through the walls. There is no sensing or control.",
  "Estimate how long the store stays cold",
  "charger:Solar charger:source;store:Cold store:buffer;clinic:Clinic:consumer;leak:Heat gain:dissipater",
  "charger>flows_to>store;store>flows_to>clinic;store>dissipates_to>leak",
  [("hard", "Store has a limited capacity")], [], "buffer with draw and loss"), [
  L("energy_thermal_storage_tank", 2, "charger:heater,store:tank,clinic:demand,leak:loss",
    "Four nodes and three edges correspond. A buffer with a draw and a loss path."),
  L("me_flywheel", 1, "charger:engine,store:flywheel,clinic:load,leak:bearing",
    "A buffer between a source and a load with a loss maps. The shaft conduit has no counterpart."),
  L("log_safety_stock", 1, "charger:supply,store:safety,clinic:demand",
    "Source, buffer, consumer maps. No loss path, a variability constraint instead."),
  L("energy_battery_soc", 1, "charger:charger,store:cells,clinic:load",
    "Charger, storage, load maps but the candidate adds a sensing loop that inhibits the charger and load."),
  L("energy_pumped_hydro", 0, "", "Two buffers exchanging through a transformer, with production to the grid. The query has one buffer and no transformer.",
    "shares the words storage, buffer and consumer with the query but has two buffers and a loop")])

add(query("hq_cholesterol_synthesis", "Liver cholesterol synthesis", "biology",
  "A precursor enters a synthesis enzyme that feeds the pathway. The pathway makes cholesterol, which cells use. Cholesterol in the pool blocks the enzyme, "
  "so synthesis falls when the pool is full.",
  "Explain how the pool is held steady",
  "precursor:Precursor:source;hmg:Synthesis enzyme:regulator;pathway:Synthesis pathway:conduit;chol:Cholesterol pool:buffer;cells:Cells:consumer",
  "precursor>flows_to>hmg;hmg>flows_to>pathway;pathway>produces>chol;chol>inhibits>hmg;chol>flows_to>cells",
  [("hard", "Enzyme rate has a maximum")], [], "end product inhibition"), [
  L("bio_end_product_inhibition", 2, "precursor:substrate,hmg:enzyme1,pathway:pathway,chol:product,cells:demand",
    "Five nodes and five edges correspond one to one."),
  L("me_float_valve_cistern", 1, "precursor:mains,hmg:inlet,chol:tank,cells:outlet",
    "A buffer that closes its own inlet maps. The candidate has an extra sensor node and no production step."),
  L("bio_calcium_homeostasis", 1, "precursor:intake,chol:plasma,cells:excretion",
    "A regulated pool with a controller loop maps. The candidate senses and controls through two extra nodes and has a different feedback target."),
  L("bio_lac_operon", 0, "", "An induction switch, with inhibition of a repressor. The substrate is consumed by enzymes it induces, so the loop is reversed.",
    "shares the words enzymes, inhibits and substrate with the query but is an induction loop")])

add(query("hq_yeast_vat", "Yeast in a closed vat", "chemistry",
  "Yeast cells divide and so their number grows faster as the culture grows. As the culture grows, ethanol accumulates and slows the division. "
  "The culture levels off at a ceiling.",
  "Explain the levelling off of the culture",
  "births:Cell division:producer;culture:Yeast culture:buffer;ethanol:Ethanol:regulator",
  "births>produces>culture;culture>activates>births;culture>activates>ethanol;ethanol>inhibits>births",
  [("hard", "Ethanol tolerance sets a ceiling")], [], "saturating growth"), [
  L("math_logistic_growth", 2, "births:growth,culture:population,ethanol:crowding",
    "Three nodes and four edges correspond one to one."),
  L("eco_fishery_harvest", 1, "births:growth,culture:stock,ethanol:capacity",
    "Growth fed by stock and a capacity limit on growth map. The candidate also has a harvest sink and an effort actuator."),
  L("eco_island_biogeography", 1, "culture:island,ethanol:extinction",
    "A stock inhibiting its own inflow and activating a loss maps. The source and the immigration node differ."),
  L("chem_autocatalysis", 1, "births:rate,culture:product",
    "Self-activation maps. There is no limiting regulator."),
  L("econ_solow_accumulation", 0, "", "Capital produces output that is saved back into capital. The loop is saturating only through depreciation and has a different wiring.",
    "shares the words stock, produces and accumulation with the query but has a different wiring")])

add(query("hq_taxi_rank", "Taxi rank with a marshal", "transportation",
  "Taxis arrive at a rank. Riders take taxis from the rank. When the rank is empty the marshal stops riders joining, and when it is full the marshal stops more taxis. "
  "The marshal releases taxis to the street.",
  "Keep the rank neither empty nor overfull",
  "taxis:Arriving taxis:source;rank:Taxi rank:buffer;riders:Riders:consumer;marshal:Marshal:regulator;street:Street:sink",
  "taxis>flows_to>rank;riders>consumes>rank;rank>inhibits>marshal;marshal>inhibits>riders;marshal>flows_to>street",
  [("hard", "Rank length is a maximum")], [], "bounded buffer with a gate"), [
  L("cs_token_bucket", 2, "taxis:refill,rank:bucket,riders:requests,marshal:limiter,street:output",
    "Refill, bucket, requests that consume it, a limiter inhibited by the bucket and inhibiting requests. All five edges correspond."),
  L("cs_bounded_buffer", 1, "taxis:producer,rank:buffer,riders:consumer,marshal:semaphore",
    "A buffer gating both its producer and its consumer maps. The wiring of the gate differs and there is no exit node."),
  L("log_conwip", 1, "taxis:release,rank:wip,marshal:cards,street:finished",
    "A capped buffer with a signal back to the release maps. The candidate has a transformer line in between."),
  L("cs_cache_hierarchy", 0, "", "A chain of buffers consuming from each other and no regulator or limit. Check 3 fails.",
    "shares the words buffer, consumer and consumes with the query but is a chain without a gate")])

add(query("hq_wine_to_vinegar", "Wine ageing to vinegar", "chemistry",
  "Grape sugar is converted into wine. The wine is converted into vinegar. Nothing returns to the earlier stages.",
  "Predict the amount of each stage over time",
  "sugar:Grape sugar:source;wine:Wine:buffer;vinegar:Vinegar:sink",
  "sugar>converts>wine;wine>converts>vinegar",
  [("hard", "Mass is conserved")], [], "sequential conversion"), [
  L("chem_series_reaction", 2, "sugar:a,wine:b,vinegar:c",
    "Three nodes and two edges correspond one to one."),
  L("phys_decay_chain", 2, "sugar:parent,wine:daughter,vinegar:stable",
    "Three nodes and two edges correspond one to one."),
  L("math_mm1_queue", 1, "sugar:arrivals,wine:queue,vinegar:departures",
    "A source to a stage to a sink maps. The candidate adds a server node and flows rather than conversion."),
  L("math_sir_epidemic", 1, "sugar:susceptible,wine:infected,vinegar:recovered",
    "A three stage chain with conversions maps. The candidate adds a feedback edge."),
  L("chem_le_chatelier", 0, "", "Reversible conversion between buffers with a control on equilibrium. The query is irreversible and has no control.",
    "shares the words converts and reactants or products with the query but is reversible")])

add(query("hq_airline_hub", "Airline hub network", "transportation",
  "Passengers from two origin cities fly into a hub airport. From the hub a long haul route carries them to two destinations.",
  "Understand how passengers merge and split at a hub",
  "city_a:Origin city A:source;city_b:Origin city B:source;hub:Hub airport:junction;longhaul:Long haul route:conduit;dest_x:Destination X:sink;dest_y:Destination Y:sink",
  "city_a>flows_to>hub;city_b>flows_to>hub;hub>flows_to>longhaul;longhaul>flows_to>dest_x;longhaul>flows_to>dest_y",
  [("hard", "Route capacity is a maximum")], [], "merge, trunk, split"), [
  L("log_hub_and_spoke", 2, "city_a:origin1,city_b:origin2,hub:hub,longhaul:trunk,dest_x:dest1,dest_y:dest2",
    "Six nodes and five edges correspond one to one."),
  L("log_transshipment_network", 1, "city_a:supply,hub:transfer,longhaul:arc,dest_x:demand",
    "Supply through an arc to a transfer to demand maps, with one origin and one destination. The arc constraint has no counterpart."),
  L("log_cross_docking", 1, "city_a:inbound,hub:dock,dest_x:outbound",
    "Inbound to a junction to outbound maps. No trunk conduit and a sort and staging stage."),
  L("phys_resistor_network", 0, "", "A single source splits into two branches and recombines. The query merges two sources then splits, so the wiring is wrong.",
    "shares source, junction, conduit and sink role types with the query but splits then merges")])


def build():
    ids = set()
    for fp in glob.glob(os.path.join(ROOT, "data", "seed_knowledge", "*.json")) + glob.glob(os.path.join(ROOT, "data", "mechanisms", "*.json")):
        with open(fp) as f:
            ids |= {s["id"] for s in json.load(f)["systems"]}
    out = []
    for q, labels in Q:
        for lab in labels:
            assert lab["system_id"] in ids, f"unknown system id {lab['system_id']} in {q['id']}"
            assert lab["grade"] in (0, 1, 2)
            assert lab["rationale"].strip()
        assert len({l["system_id"] for l in labels}) == len(labels), q["id"]
        assert any(l["grade"] == 2 for l in labels), q["id"]
        assert sum(1 for l in labels if l["grade"] < 2) >= 2, q["id"]
        assert any(l["lookalike"] for l in labels), q["id"]
        q = dict(q)
        q.pop("acceptable", None)
        out.append({"query": q, "labels": labels})
    return out


def main():
    items = build()
    doc = {"description": "Held-out structural analog set (split: heldout). Labels are author_labelled, independent_review none. "
                          "Written from docs/labelling-guide.md before any matcher run. The author also wrote the matcher, "
                          "so this set is less overlapping with the tuning set but is NOT independent.",
           "split": "heldout", "label_status": "author_labelled", "independent_review": "none",
           "grades": {"2": "strong analog", "1": "partial analog", "0": "not analog (lookalike if lookalike true)"},
           "items": items}
    with open(os.path.join(ROOT, "data", "benchmark_problems", "heldout_labels.json"), "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    rows = []
    for it in items:
        for lab in it["labels"]:
            rows.append({"item_id": f"{it['query']['id']}::{lab['system_id']}", "query_id": it["query"]["id"],
                         "system_id": lab["system_id"], "author_grade": lab["grade"], "reviewer_grade": None,
                         "agree": None, "role_mapping_correct": None, "comment": "",
                         "reviewer_name": "", "review_date": ""})
    tdoc = {"description": "Blank review template, one row per held-out label. A reviewer fills reviewer_grade (0, 1 or 2), agree (true/false), "
                           "role_mapping_correct (true/false), comment, reviewer_name and review_date, following docs/labelling-guide.md. "
                           "Do not look at matcher scores. Save the filled file elsewhere and run scripts/compare_reviews.py on it.",
            "review_status": "not_reviewed", "rows": rows}
    with open(os.path.join(ROOT, "data", "benchmark_problems", "review_template.json"), "w") as f:
        json.dump(tdoc, f, indent=1)
        f.write("\n")
    print(f"wrote {len(items)} queries, {len(rows)} labels")


if __name__ == "__main__":
    main()
