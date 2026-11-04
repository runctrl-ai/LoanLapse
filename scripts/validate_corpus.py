#!/usr/bin/env python3
"""Reviewer-POV consistency audit for the L1 corpus (datasets/corpus/L1/v1.0.0).

Checks, per case: required files + case_id agreement; boundary/gate agreement and that the
boundary is declared in policy; that every fired contract is defined and binds that boundary;
provenance/temporal ordering (proposal is the last event, no evidence postdates it, trace in
order); actor authorization (proposer in boundary_roles unless it is a wrong-actor DENY, and
the trace's proposing agent matches the proposal actor); referential integrity (package refs,
cited docs, condition ids, stale chain, dropped/injection seqs); and mode/label invariants
(clean/handled->ALLOW, pending->HOLD, defect->HOLD/DENY; DENY only for F-SOD; V0/V3 never DENY).
Finally cross-checks index.jsonl and MANIFEST.json against the folders. Exit 1 on any error.
"""
import json, pathlib, sys, yaml
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parent.parent
ROOT = REPO / "datasets" / "corpus" / "L1" / "v1.0.0"
POLICY = REPO / "policy" / "contracts.yaml"

GATE_OF = {"submit_to_underwriting": "A", "mark_conditions_cleared": "B", "render_decision": "C"}

pol = yaml.safe_load(POLICY.read_text())
DEFINED = {c["id"] for c in pol["contracts"]}
DECLARED_BOUNDARIES = set(pol["boundaries"])
BOUNDARY_ROLES = pol["boundary_roles"]
CONTRACT_BOUNDARIES = {c["id"]: {b["boundary"] for b in c["binds"]} for c in pol["contracts"]}

def parse(ts): return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")

errs, warns = [], []
def err(cid, m): errs.append(f"{cid}: {m}")

dirs = [d for d in sorted(ROOT.iterdir()) if d.is_dir()]
counts = {"ALLOW": 0, "HOLD": 0, "DENY": 0}
index_rows = []

for d in dirs:
    cid = d.name
    files = {f.stem: json.loads(f.read_text()) for f in d.glob("*.json")}
    required = ["case", "evidence", "obligations", "trace", "proposal", "reference"]
    if any(r not in files for r in required):
        for r in required:
            if r not in files: err(cid, f"missing {r}.json")
        continue
    case, ev, ob, tr, pr, ref = (files[k] for k in required)
    var, gt, boundary = case["variation"], ref["ground_truth"], ref["boundary"]
    fam = case["family_ids"][0]
    mode = cid.split("__")[1].split("-")[0]
    counts[gt] = counts.get(gt, 0) + 1
    index_rows.append({"case_id": cid, "family": fam, "issue_id": case["issue_id"],
                       "variation": var, "gate": case["gate"], "ground_truth": gt})

    # --- case_id agreement ---
    for k, obj in files.items():
        if obj.get("case_id") != cid: err(cid, f"{k}.json case_id={obj.get('case_id')}")

    # --- boundary / gate ---
    if pr["boundary"] != boundary: err(cid, f"proposal boundary {pr['boundary']} != reference {boundary}")
    if boundary not in DECLARED_BOUNDARIES: err(cid, f"boundary {boundary} not declared in policy")
    if case["gate"] != GATE_OF.get(boundary): err(cid, f"gate {case['gate']} != gate_of({boundary})")

    # --- contracts ---
    for c in ref.get("contracts_fired", []):
        if c not in DEFINED: err(cid, f"contract {c} fired but not defined in policy")
        elif boundary not in CONTRACT_BOUNDARIES[c]:
            err(cid, f"contract {c} fired at {boundary} but does not bind there")

    # --- temporal / provenance ---
    ev_ts = []
    for dd in ev["documents"]:
        for kk in ("received_at", "generated_at"):
            if dd.get(kk): ev_ts.append(dd[kk])
    for c in ev["connectors"]:
        if c.get("attempted_at"): ev_ts.append(c["attempted_at"])
    pat = pr["proposed_at"]
    if pat != tr["events"][-1]["at"]:
        err(cid, f"proposed_at {pat} != last trace event {tr['events'][-1]['at']}")
    for t in ev_ts:
        if parse(t) > parse(pat): err(cid, f"evidence {t} postdates proposal {pat}")
    ats = [e["at"] for e in tr["events"]]
    if [parse(a) for a in ats] != sorted(parse(a) for a in ats):
        err(cid, "trace events not in chronological order")
    seqs = [e["seq"] for e in tr["events"]]
    if seqs != list(range(1, len(seqs) + 1)): err(cid, f"trace seqs not 1..n: {seqs}")

    # --- actor authorization ---
    role = pr["actor"]["role"]
    allowed = BOUNDARY_ROLES.get(boundary, [])
    if gt == "DENY":
        if role in allowed: err(cid, f"DENY but proposer {role} IS allowed at {boundary}")
    else:
        if role not in allowed: err(cid, f"{gt} but proposer {role} NOT allowed at {boundary}")
    last_agent = tr["events"][-1]["agent"]
    if last_agent != role: err(cid, f"trace propose agent {last_agent} != proposal actor role {role}")

    # --- referential integrity ---
    docvers = {}
    for dd in ev["documents"]:
        docvers.setdefault(dd["id"], set()).add(dd["version"])
    comp_ids = {r["id"] for r in ev["computed_results"]}
    ob_ids = {o["id"] for o in ob["obligations"]}
    for r in ev["computed_results"]:
        for did, dv in r.get("inputs", {}).items():
            if dv not in docvers.get(did, set()): err(cid, f"result {r['id']} cites {did} v{dv} absent")
    pkg = pr["package"]
    for k, v in pkg.items():
        if k.endswith("_ref") and isinstance(v, str) and v not in comp_ids:
            err(cid, f"package {k}={v} not in computed_results")
    for dc in pkg.get("documents_cited", []):
        if dc not in docvers: err(cid, f"package cites unknown doc {dc}")
    for c in pkg.get("condition_ids", []):
        if c not in ob_ids: err(cid, f"package condition {c} not in obligations")
    for sc in ref.get("stale_chain", []):
        if sc not in comp_ids: err(cid, f"stale_chain {sc} not in computed_results")
    if "dropped_at_seq" in ref and ref["dropped_at_seq"] not in seqs:
        err(cid, f"dropped_at_seq {ref['dropped_at_seq']} not a trace seq")
    if "injection" in files:
        for inj in files["injection"]["injections"]:
            if inj.get("at_seq") not in seqs: err(cid, f"injection at_seq {inj.get('at_seq')} not a trace seq")

    # --- mode / label invariants ---
    expect = {"clean": {"ALLOW"}, "handled": {"ALLOW"}, "pending": {"HOLD"}, "defect": {"HOLD", "DENY"}}
    if gt not in expect.get(mode, set()): err(cid, f"mode {mode} but ground_truth {gt}")
    if gt == "DENY" and fam != "F-SOD": err(cid, f"DENY outside F-SOD (family {fam})")
    if gt == "DENY" and var in ("V0", "V3"): err(cid, f"{var} case is DENY (control space forbids)")
    if var not in ("V0", "V1", "V2", "V3"): err(cid, f"bad variation {var}")

    # --- injection presence ---
    if var in ("V2", "V3") and "injection" not in files: err(cid, f"{var} missing injection.json")
    if var == "V0" and "injection" in files: err(cid, f"V0 has injection.json")

    # --- defect detection-class / compositionality ---
    RECOUNT_FAMS = {"F-COMP", "F-UNK", "F-LOSS"}
    if mode == "defect":
        if ref.get("all_local_steps_pass") is not True: err(cid, "defect missing all_local_steps_pass")
        dc = ref.get("detection_class")
        if gt == "DENY":
            if dc != "single_point_authority": err(cid, f"DENY defect detection_class={dc} (want single_point_authority)")
            if ref.get("no_single_culprit") is not False: err(cid, "DENY defect should have no_single_culprit=false (single-point authority)")
        elif fam in RECOUNT_FAMS:
            if dc != "single_point_recount": err(cid, f"{fam} HOLD defect detection_class={dc} (want single_point_recount)")
            if ref.get("no_single_culprit") is not False: err(cid, "single_point_recount defect should have no_single_culprit=false")
        else:  # compositional HOLD defect
            if dc != "compositional": err(cid, f"HOLD defect detection_class={dc} (want compositional)")
            if ref.get("no_single_culprit") is not True: err(cid, "compositional defect missing no_single_culprit=true")

# --- index.jsonl & MANIFEST cross-check ---
idx_path = ROOT / "index.jsonl"
if idx_path.exists():
    idx = [json.loads(l) for l in idx_path.read_text().splitlines() if l.strip()]
    if len(idx) != len(dirs): err("index.jsonl", f"{len(idx)} rows != {len(dirs)} case folders")
    by_id = {r["case_id"]: r for r in idx}
    for row in index_rows:
        got = by_id.get(row["case_id"])
        if not got: err("index.jsonl", f"missing {row['case_id']}")
        elif got != row: err("index.jsonl", f"{row['case_id']} mismatch {got} != {row}")
else:
    err("index.jsonl", "missing")

man_path = ROOT / "MANIFEST.json"
if man_path.exists():
    man = json.loads(man_path.read_text())
    if man.get("total_cases") != len(dirs): err("MANIFEST", f"total {man.get('total_cases')} != {len(dirs)}")
    if man.get("label_counts") != counts: err("MANIFEST", f"label_counts {man.get('label_counts')} != {counts}")
else:
    err("MANIFEST", "missing")

if errs:
    print(f"PROBLEMS ({len(errs)}):")
    for e in errs[:200]:
        print(" -", e)
    sys.exit(1)
print(f"all consistency checks passed on {len(dirs)} corpus cases")
print(f"labels: {counts}")
