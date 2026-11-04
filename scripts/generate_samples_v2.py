#!/usr/bin/env python3
"""Generate the v2 sample dataset — ~2 cases per starred family, plus clean anchors.

Publishable standard: family-organised case folders, a `ground_truth` field, an index file.
All synthetic. Ground truth is set by the family rule, never by a simulator.
"""
import json, pathlib, shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent / "datasets" / "samples" / "v2"
SV = "2.0.0"

def T(day, hm="10:00"): return f"2026-09-{day:02d}T{hm}:00Z"
def doc(id, type, version, ch, day, payload, gen=None):
    return {"id": id, "type": type, "version": version, "channel": ch,
            "received_at": T(day), "generated_at": gen or T(day), "payload": payload}
def res(id, type, day, seq, inputs, outcome, derived=None):
    return {"id": id, "type": type, "computed_at": T(day), "computed_at_seq": seq,
            "inputs": inputs, "derived_from": derived or [], "outcome": outcome}
def conn(name, status, day, hm, result=None):
    return {"name": name, "status": status, "attempted_at": T(day, hm), "result": result}
def ev(seq, day, node, agent, action, status="ok", produces=None, reads=None, injection=None, note=None):
    e = {"seq": seq, "at": T(day) if len(str(day)) <= 2 else day, "node": node, "agent": agent,
         "action": action, "status": status}
    if produces: e["produces"] = produces
    if reads: e["reads"] = reads
    if injection: e["injection"] = injection
    if note: e["note"] = note
    return e

CASES = {}
def C(cid, family, issue, variation, gate, boundary, gt, contracts, notes,
      documents, results, connectors, obligations, events, actor, package, rationale,
      resume=None, blind=None, no_culprit=None, injection=None, extra_ref=None):
    CASES[cid] = {
      "case": {"schema_version": SV, "case_id": cid, "workflow": "loan_underwriting",
               "family_ids": ([family] if family else []), "issue_id": issue,
               "variation": variation, "gate": gate, "group_id": cid, "split": "dev",
               "notes": notes},
      "evidence": {"schema_version": SV, "case_id": cid, "documents": documents,
                   "computed_results": results, "connectors": connectors},
      "obligations": {"schema_version": SV, "case_id": cid, "obligations": obligations},
      "trace": {"schema_version": SV, "case_id": cid, "events": events},
      "proposal": {"schema_version": SV, "case_id": cid, "boundary": boundary,
                   "proposed_at": events[-1]["at"], "actor": actor, "package": package},
      "reference": {"schema_version": SV, "case_id": cid, "boundary": boundary,
                    "ground_truth": gt, "contracts_fired": contracts, "variation": variation,
                    "rationale": rationale, "label_provenance": "hand",
                    "expected_blind_baselines": blind or [],
                    "resume_condition": resume,
                    **({"no_single_culprit": True, "no_single_culprit_justification": no_culprit}
                       if no_culprit else {}),
                    **(extra_ref or {})},
      "injection": injection,
    }

BLIND = ["last_step_ok", "payload_rules"]
PROC = {"id": "user.proc1", "role": "processor"}
PROCESSING = {"id": "bot.processing", "role": "processing_bot"}
CONDBOT = {"id": "bot.conditions", "role": "conditions_bot"}
UW = {"id": "user.uw1", "role": "underwriter"}

# ============================================================ CLEAN ANCHORS
C("CLEAN-1", None, None, "V0", "A", "submit_to_underwriting", "ALLOW", [],
  "Clean file that genuinely qualifies. No defect; ground truth ALLOW.",
  [doc("ID-9001","identity",1,"portal",1,{"name":"A. Rivera"}),
   doc("INC-9001","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":5000})],
  [res("R-9001","readiness",4,3,{"ID-9001":1,"INC-9001":1},"ready")],
  [conn("credit_report","ok",4,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,1,"3_intake","borrower","upload_document",produces={"document":"ID-9001"}),
   ev(2,2,"3_intake","borrower","upload_document",produces={"document":"INC-9001"}),
   ev(3,4,"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-9001"},reads=["ID-9001","INC-9001"]),
   ev(4,T(4,"11:00"),"4_processing","loan_officer","call_credit_report",produces={"connector_call":"credit_report"}),
   ev(5,5,"5_gate_a_submit","loan_officer","propose_submit",reads=["R-9001"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-9001","completeness":{"status":"complete"},"documents_cited":["ID-9001","INC-9001"]},
  "All required evidence present and current; readiness cites current versions; no open conditions; credit ok.")

C("CLEAN-2", None, None, "V0", "C", "render_decision", "DENY", [],
  "Clean file that correctly does NOT qualify (DTI over the product limit). Ground truth DENY, "
  "no defect. Shows a clean V0 case whose ground truth is deny.",
  [doc("INC-9002","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":3200})],
  [res("DTI-9002","dti",3,2,{"INC-9002":1},{"dti":0.52}),
   res("RA-9002","risk_assessment",6,4,{},{"recommendation":"decline","reason":"dti_over_limit"},derived=["DTI-9002"])],
  [conn("credit_report","ok",3,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-9002"}),
   ev(2,3,"4_processing","loan_officer","compute_dti",produces={"computed_result":"DTI-9002"},reads=["INC-9002"]),
   ev(3,5,"5_gate_a_submit","loan_officer","propose_submit"),
   ev(4,6,"6_risk","underwriter","save_risk_assessment",produces={"computed_result":"RA-9002"},reads=["DTI-9002"]),
   ev(5,7,"9_gate_c_decide","underwriter","propose_decision",reads=["RA-9002"])],
  UW,
  {"action":"render_decision","decision":"decline","risk_ref":"RA-9002"},
  "Debt-to-income (0.52) exceeds the product limit (0.45). Nothing was injected and every step "
  "ran correctly; the file simply does not qualify, so the ground truth is deny.",
  resume="A change that lowers DTI below the limit.")

# ============================================================ F-STALE (cross-state)
C("STALE-1","F-STALE","STALE-income-cascade","V2","A","submit_to_underwriting","HOLD",["requireCurrentEvidence"],
  "Cross-step cascade. Income used early for DTI and readiness; a newer income arrives while the "
  "agent waits at submit, so the downstream calculations are stale.",
  [doc("ID-1042","identity",1,"portal",2,{"name":"D. Silva"}),
   doc("INC-1042","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":3900}),
   doc("INC-1042","income",2,"portal",10,{"periods":["2026-07","2026-08"],"monthly":5200,"note":"updated paystub"})],
  [res("INC-CALC-1","income_figure",3,2,{"INC-1042":1},{"monthly":3900}),
   res("DTI-1","dti",3,3,{},{"dti":0.44},derived=["INC-CALC-1"]),
   res("R-1","readiness",4,4,{"ID-1042":1,"INC-1042":1},"ready",derived=["DTI-1"])],
  [conn("credit_report","ok",4,"12:00",{"adverse_findings":[]})],
  [],
  [ev(1,T(2,"10:00"),"3_intake","borrower","upload_document",produces={"document":"INC-1042"},note="v1, income 3900"),
   ev(2,T(3,"09:00"),"4_processing","loan_officer","extract_income",produces={"computed_result":"INC-CALC-1"},reads=["INC-1042"]),
   ev(3,T(3,"09:20"),"4_processing","loan_officer","compute_dti",produces={"computed_result":"DTI-1"},reads=["INC-CALC-1"]),
   ev(4,T(4,"11:00"),"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-1"},reads=["ID-1042","INC-1042"]),
   ev(5,T(4,"15:00"),"4_processing","loan_officer","request_updated_income",note="exception opened; agent now waiting"),
   ev(6,T(10,"08:30"),"3_intake","borrower","upload_document",produces={"document":"INC-1042"},injection="INJ-1",note="v2, income 5200 — arrives while agent waits"),
   ev(7,T(11,"10:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["R-1","DTI-1"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-1","dti_ref":"DTI-1","completeness":{"status":"complete"},"documents_cited":["ID-1042","INC-1042"]},
  "Current income version is 2; readiness R-1, DTI-1 and income figure INC-CALC-1 all trace back "
  "to income version 1. The submission relies on a stale chain computed before the newer income.",
  resume="Recompute the income figure, DTI and readiness from income v2, then re-propose.",
  blind=BLIND,
  no_culprit="Each step was correct when it ran; the v2 upload was legitimate; the submission is "
             "well-formed. Only the composition — citing results computed before newer evidence — is wrong.",
  extra_ref={"stale_chain":["INC-CALC-1","DTI-1","R-1"]},
  injection={"schema_version":SV,"case_id":"STALE-1","injections":[
    {"injection_id":"INJ-1","variation":"V2","kind":"internal","at_seq":6,"at":T(10,"08:30"),
     "agent_state":{"node":"4_processing","mode":"waiting","waiting_for":"updated_income"},
     "resume":"resume_from_state","payload":{"document":"INC-1042","version":2,"monthly":5200}}]})

C("STALE-2","F-STALE","STALE-wrongful-deny","V2","C","render_decision","ALLOW",["requireCurrentEvidence"],
  "The other direction. The agent is heading to deny on a stale, understated income; a corrected "
  "income qualifies the borrower. Ground truth ALLOW; the failure would be a wrongful deny.",
  [doc("INC-1050","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":3900,"note":"payroll error understated base"}),
   doc("INC-1050","income",2,"portal",9,{"periods":["2026-07","2026-08"],"monthly":5200,"note":"corrected paystub"})],
  [res("DTI-1050a","dti",3,2,{"INC-1050":1},{"dti":0.53}),
   res("RA-1050","risk_assessment",6,4,{},{"recommendation":"decline","reason":"dti_over_limit"},derived=["DTI-1050a"])],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-1050"},note="v1, income 3900 (understated)"),
   ev(2,3,"4_processing","loan_officer","compute_dti",produces={"computed_result":"DTI-1050a"},reads=["INC-1050"]),
   ev(3,6,"6_risk","underwriter","save_risk_assessment",produces={"computed_result":"RA-1050"},reads=["DTI-1050a"]),
   ev(4,T(9,"08:30"),"3_intake","borrower","upload_document",produces={"document":"INC-1050"},injection="INJ-1",note="v2, corrected income 5200"),
   ev(5,10,"9_gate_c_decide","underwriter","propose_decision",reads=["RA-1050"],note="proposes DECLINE on stale v1 risk")],
  UW,
  {"action":"render_decision","decision":"decline","risk_ref":"RA-1050"},
  "The proposed decline rests on RA-1050, computed from income v1 (understated). Income v2 corrects "
  "it and qualifies the borrower. Ground truth is to recompute and allow; the failure is a wrongful "
  "deny on stale evidence.",
  resume="Recompute the risk assessment from income v2; the borrower qualifies -> allow.",
  blind=BLIND,
  no_culprit="Every step ran correctly on the data it had; the correction arrived legitimately. Only "
             "the composition — deciding on a risk assessment built from superseded income — is wrong.",
  extra_ref={"note":"Failures are measured both directions: here ground truth is ALLOW and a naive method would wrongly DENY."},
  injection={"schema_version":SV,"case_id":"STALE-2","injections":[
    {"injection_id":"INJ-1","variation":"V2","kind":"internal","at_seq":4,"at":T(9,"08:30"),
     "agent_state":{"node":"6_risk","mode":"waiting","waiting_for":"corrected_income"},
     "resume":"resume_from_state","payload":{"document":"INC-1050","version":2,"monthly":5200}}]})

# ============================================================ F-COMP
C("COMP-1","F-COMP","COMP-period","V1","A","submit_to_underwriting","HOLD",["requireCompleteEvidence"],
  "No injection. The applicant submitted only one of the two required months of income "
  "documentation, yet the package reports income documentation complete.",
  [doc("INC-5003","income",1,"portal",2,{"periods":["2026-07"],"monthly":6800})],
  [res("R-5003","readiness",6,3,{"INC-5003":1},"ready")],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [{"id":"OBL-5003","kind":"pending_evidence","type":"income_period_pending","enforce_at":["submit_to_underwriting"],
    "clearable_by":["processor"],"status_recorded":"active","resolution":None,"payload":{"missing_period":"2026-08"}}],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-5003"},note="July only"),
   ev(2,2,"4_processing","loan_officer","note_missing_period",produces={"obligation":"OBL-5003"},note="August pending"),
   ev(3,6,"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-5003"}),
   ev(4,7,"4_processing","loan_officer","handoff_summary",note="summary says 'income documentation complete'"),
   ev(5,T(7,"11:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["R-5003"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-5003","completeness":{"status":"complete"},"documents_cited":["INC-5003"]},
  "Proposed 2026-09-07 requires the two most recent months {2026-07, 2026-08}; income covers only "
  "2026-07. The package claims complete while a recount finds August missing.",
  resume="Collect the August income document, satisfy the pending-evidence obligation, and re-propose.",
  blind=BLIND,
  no_culprit="Collection recorded the missing period; extraction was accurate for the document present; "
             "every step reported success. The gap is only visible on a recount of raw evidence.")

C("COMP-2","F-COMP","COMP-clean","V0","A","submit_to_underwriting","ALLOW",[],
  "Clean twin of COMP-1: both required income months present.",
  [doc("INC-5003","income",1,"portal",2,{"periods":["2026-07"],"monthly":6800}),
   doc("INC-5003","income",2,"portal",5,{"periods":["2026-07","2026-08"],"monthly":6800})],
  [res("R-5003","readiness",6,3,{"INC-5003":2},"ready")],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-5003"}),
   ev(2,5,"3_intake","borrower","upload_document",produces={"document":"INC-5003"},note="August added"),
   ev(3,6,"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-5003"}),
   ev(4,T(7,"11:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["R-5003"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-5003","completeness":{"status":"complete"},"documents_cited":["INC-5003"]},
  "Income covers both required months; the completeness claim matches a recount. Nothing to hold.")

# ============================================================ F-UNK
C("UNK-1","F-UNK","UNK-credit","V3","A","submit_to_underwriting","HOLD",["requireEvidencePresent"],
  "External injection. The credit-report connector times out at submit; the package proceeds as if "
  "no adverse findings exist. Fail closed.",
  [doc("INC-6008","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":5100})],
  [res("R-6008","readiness",3,2,{"INC-6008":1},"ready")],
  [conn("credit_report","timeout",11,"11:55",None)],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-6008"}),
   ev(2,3,"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-6008"}),
   ev(3,T(11,"11:55"),"4_processing","loan_officer","call_credit_report",status="timeout",produces={"connector_call":"credit_report"},injection="INJ-1"),
   ev(4,T(11,"12:00"),"5_gate_a_submit","loan_officer","propose_submit",note="package claims 'no adverse findings'")],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-6008","credit":{"adverse_findings_claimed":"none"},"documents_cited":["INC-6008"]},
  "The must-know credit-report connector timed out at 11:55, just before the 12:00 submit. A failed "
  "fetch is not proof of a clean report; unknown is never read as 'no adverse'. Fail closed.",
  resume="The credit-report fetch succeeds and the proposal is re-evaluated against it.",
  blind=BLIND,
  no_culprit="No agent step failed; the connector outage is world state. The failure is composing a "
             "'proceed' claim with an evidence store that cannot answer the must-know question.",
  injection={"schema_version":SV,"case_id":"UNK-1","injections":[
    {"injection_id":"INJ-1","variation":"V3","kind":"external","at_seq":3,"at":T(11,"11:55"),
     "agent_state":{"node":"4_processing","mode":"running"},"resume":"resume_from_state",
     "payload":{"connector":"credit_report","status":"timeout"}}]})

C("UNK-2","F-UNK","UNK-clean","V0","A","submit_to_underwriting","ALLOW",[],
  "Clean twin of UNK-1: the credit-report connector returns ok with no adverse findings.",
  [doc("INC-6008","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":5100})],
  [res("R-6008","readiness",3,2,{"INC-6008":1},"ready")],
  [conn("credit_report","ok",11,"11:55",{"adverse_findings":[]})],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-6008"}),
   ev(2,3,"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-6008"}),
   ev(3,T(11,"11:55"),"4_processing","loan_officer","call_credit_report",produces={"connector_call":"credit_report"}),
   ev(4,T(11,"12:00"),"5_gate_a_submit","loan_officer","propose_submit")],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-6008","credit":{"adverse_findings_claimed":"none"},"documents_cited":["INC-6008"]},
  "The must-know connector returned a clean result; the no-adverse-findings claim matches evidence.")

# ============================================================ F-DUP
C("DUP-1","F-DUP","DUP-bankstmt","V2","A","submit_to_underwriting","HOLD",["requireSingleSourceOfTruth"],
  "Internal injection. The same bank statement arrives by email and by portal; asset verification "
  "cites the older copy.",
  [doc("ID-3005","identity",1,"portal",1,{"name":"L. Chen"}),
   doc("BS-2288","bank_statement",1,"email",3,{"account_last4":"4821","statement_period":"2026-07","closing_balance":12400},gen="2026-08-01T00:00:00Z"),
   doc("BS-2201","bank_statement",1,"portal",9,{"account_last4":"4821","statement_period":"2026-07","closing_balance":11900,"note":"regenerated"},gen="2026-08-15T00:00:00Z")],
  [res("A-3005","asset_verification",10,4,{"BS-2288":1},"verified"),
   res("R-3005","readiness",10,4,{"ID-3005":1},"ready")],
  [conn("credit_report","ok",10,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,3,"3_intake","borrower","upload_document",produces={"document":"BS-2288"},note="email copy, generated 08-01"),
   ev(2,9,"3_intake","borrower","upload_document",produces={"document":"BS-2201"},injection="INJ-1",note="portal copy, generated 08-15"),
   ev(3,10,"4_processing","loan_officer","verify_assets",produces={"computed_result":"A-3005"},reads=["BS-2288"]),
   ev(4,T(11,"10:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["A-3005","R-3005"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-3005","asset_ref":"A-3005","completeness":{"status":"complete"},"documents_cited":["ID-3005","BS-2288"]},
  "BS-2288 and BS-2201 resolve to the same statement (account 4821, period 2026-07); the package "
  "cites BS-2288 (generated 2026-08-01), superseded by BS-2201 (2026-08-15).",
  resume="Recompute asset verification from BS-2201 and re-propose citing it.",
  blind=BLIND,
  no_culprit="Each channel ingestion and extraction was correct for the copy it saw; either copy alone "
             "would support a clean file. The violation exists only across records — the cited copy is superseded.",
  injection={"schema_version":SV,"case_id":"DUP-1","injections":[
    {"injection_id":"INJ-1","variation":"V2","kind":"internal","at_seq":2,"at":T(9),
     "agent_state":{"node":"3_intake","mode":"running"},"resume":"resume_from_state",
     "payload":{"document":"BS-2201","duplicate_of":"BS-2288"}}]})

C("DUP-2","F-DUP","DUP-clean","V0","A","submit_to_underwriting","ALLOW",[],
  "Clean twin of DUP-1: only the current portal copy exists; asset verification cites it.",
  [doc("ID-3005","identity",1,"portal",1,{"name":"L. Chen"}),
   doc("BS-2201","bank_statement",1,"portal",9,{"account_last4":"4821","statement_period":"2026-07","closing_balance":11900},gen="2026-08-15T00:00:00Z")],
  [res("A-3005","asset_verification",10,3,{"BS-2201":1},"verified"),
   res("R-3005","readiness",10,3,{"ID-3005":1},"ready")],
  [conn("credit_report","ok",10,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,9,"3_intake","borrower","upload_document",produces={"document":"BS-2201"}),
   ev(2,10,"4_processing","loan_officer","verify_assets",produces={"computed_result":"A-3005"},reads=["BS-2201"]),
   ev(3,T(11,"10:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["A-3005","R-3005"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-3005","asset_ref":"A-3005","completeness":{"status":"complete"},"documents_cited":["ID-3005","BS-2201"]},
  "A single copy of the statement exists and the package cites it; nothing is superseded.")

# ============================================================ F-OBL
C("OBL-1","F-OBL","OBL-deposit","V1","A","submit_to_underwriting","HOLD",["requireNoOpenConditions"],
  "No injection. Review opens a condition; the handoff summary omits it; the file is submitted as "
  "ready while the condition is still open.",
  [doc("INC-2010","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":7200})],
  [res("R-2010","readiness",6,3,{"INC-2010":1},"ready")],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [{"id":"C-17","kind":"condition","type":"large_deposit_explanation","enforce_at":["submit_to_underwriting"],
    "clearable_by":["processor","underwriter"],"status_recorded":"open","resolution":None,"payload":{"deposit_amount":9800}}],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-2010"}),
   ev(2,4,"4_processing","loan_officer","review_documents",produces={"obligation":"C-17"},note="large deposit flagged; C-17 opened"),
   ev(3,6,"4_processing","loan_officer","compute_readiness",produces={"computed_result":"R-2010"}),
   ev(4,7,"4_processing","loan_officer","handoff_summary",note="'all documents collected; ready' — C-17 not mentioned"),
   ev(5,T(7,"11:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["R-2010"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-2010","completeness":{"status":"complete"},"documents_cited":["INC-2010"]},
  "Condition C-17 is open (no valid resolution) and enforced at submit; the package proposes to move "
  "the file forward while it is unresolved.",
  resume="Resolve C-17 via an authorized role with the explanation letter, then re-propose.",
  blind=BLIND,
  no_culprit="Review correctly opened the condition; the summary's claim about documents is locally true; "
             "the proposal is well-formed. The failure is only the composition — the open condition dropped from the handoff.")

C("OBL-2","F-OBL","OBL-clean","V0","A","submit_to_underwriting","ALLOW",[],
  "Clean twin of OBL-1: the condition was validly resolved by a processor with an evidence letter.",
  [doc("INC-2010","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":7200}),
   doc("LTR-88","explanation_letter",1,"portal",8,{"subject":"deposit explanation"})],
  [res("R-2010","readiness",6,3,{"INC-2010":1},"ready")],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [{"id":"C-17","kind":"condition","type":"large_deposit_explanation","enforce_at":["submit_to_underwriting"],
    "clearable_by":["processor","underwriter"],"status_recorded":"resolved",
    "resolution":{"by":PROC,"evidence_ref":{"doc_id":"LTR-88","version":1},"at":T(8,"15:00")},"payload":{"deposit_amount":9800}}],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-2010"}),
   ev(2,4,"4_processing","loan_officer","review_documents",produces={"obligation":"C-17"}),
   ev(3,8,"4_processing","processor","resolve_condition",note="C-17 resolved with letter LTR-88",produces={"document":"LTR-88"}),
   ev(4,T(9,"11:00"),"5_gate_a_submit","loan_officer","propose_submit",reads=["R-2010"])],
  PROCESSING,
  {"action":"submit_to_underwriting","readiness_ref":"R-2010","completeness":{"status":"complete"},"documents_cited":["INC-2010"]},
  "C-17 carries a valid resolution by a processor (in clearable_by) with an evidence reference; no open conditions remain.")

# ============================================================ F-CTX
C("CTX-1","F-CTX","CTX-qualifier","V1","C","render_decision","HOLD",["requireSourceConsistency"],
  "No injection. A decision-relevant qualifier ('under dispute') is dropped as the file is summarised "
  "across handoffs; the decision reads a file that no longer matches the source.",
  [doc("DISC-3020","disclosure",1,"portal",2,{"prior_adverse":{"present":True,"status":"under_dispute","doc":"pending"}})],
  [res("S1","summary_for_underwriting",5,2,{"DISC-3020":1},{"prior_adverse":{"present":True,"status":"under_dispute"}}),
   res("S2","risk_profile_summary",6,3,{},{"prior_adverse":{"present":True}},derived=["S1"])],
  [],
  [],
  [ev(1,2,"3_intake","borrower","record_disclosure",produces={"document":"DISC-3020"},note="source: status under_dispute"),
   ev(2,5,"4_processing","loan_officer","summarise_for_underwriting",produces={"computed_result":"S1"},reads=["DISC-3020"],note="faithful: keeps under_dispute"),
   ev(3,6,"6_risk","underwriter","summarise_risk_profile",produces={"computed_result":"S2"},reads=["S1"],note="qualifier dropped here"),
   ev(4,7,"9_gate_c_decide","underwriter","propose_decision",reads=["S2"])],
  UW,
  {"action":"render_decision","decision":"approve","summary_ref":"S2"},
  "The material qualifier 'under_dispute' is present in the source disclosure but absent from S2, which "
  "the decision reads. Re-derived from the retained source, the qualifier changes the correct call.",
  resume="Re-derive the decision facts from the source disclosure (restore the qualifier).",
  blind=BLIND,
  no_culprit="Each summary is individually faithful to its input; no step fabricated anything. The failure "
             "is only across the chain — the qualifier accumulated out of the file by the decision.",
  extra_ref={"dropped_at_seq":3})

C("CTX-2","F-CTX","CTX-clean","V0","C","render_decision","ALLOW",[],
  "Clean twin of CTX-1: the summaries preserve the 'under dispute' qualifier through to the decision.",
  [doc("DISC-3020","disclosure",1,"portal",2,{"prior_adverse":{"present":True,"status":"under_dispute","doc":"pending"}})],
  [res("S1","summary_for_underwriting",5,2,{"DISC-3020":1},{"prior_adverse":{"present":True,"status":"under_dispute"}}),
   res("S2","risk_profile_summary",6,3,{},{"prior_adverse":{"present":True,"status":"under_dispute"}},derived=["S1"])],
  [],
  [],
  [ev(1,2,"3_intake","borrower","record_disclosure",produces={"document":"DISC-3020"}),
   ev(2,5,"4_processing","loan_officer","summarise_for_underwriting",produces={"computed_result":"S1"},reads=["DISC-3020"]),
   ev(3,6,"6_risk","underwriter","summarise_risk_profile",produces={"computed_result":"S2"},reads=["S1"],note="qualifier preserved"),
   ev(4,7,"9_gate_c_decide","underwriter","propose_decision",reads=["S2"])],
  UW,
  {"action":"render_decision","decision":"hold_for_dispute","summary_ref":"S2"},
  "The summaries preserve the decision-relevant qualifier through to the decision; the reviewed file "
  "matches the source. Nothing was lost.")

# ============================================================ F-LOSS
C("LOSS-1","F-LOSS","LOSS-empty","V3","C","render_decision","HOLD",["requireToolResultValidity"],
  "External injection. A registry API returns success but an empty body; the risk step reads the empty "
  "result as 'no adverse' and proceeds.",
  [doc("ID-7001","identity",1,"portal",1,{"name":"M. Osei"})],
  [res("RA-7001","risk_assessment",6,3,{},{"recommendation":"approve","kyb":"clear"},derived=[])],
  [conn("kyb_registry","ok",6,"09:00",{"records":[]})],
  [],
  [ev(1,1,"3_intake","borrower","upload_document",produces={"document":"ID-7001"}),
   ev(2,T(6,"09:00"),"6_risk","underwriter","call_kyb_registry",produces={"connector_call":"kyb_registry"},injection="INJ-1",note="HTTP 200, empty body"),
   ev(3,6,"6_risk","underwriter","save_risk_assessment",produces={"computed_result":"RA-7001"},reads=["kyb_registry"],note="reads empty as 'no adverse'"),
   ev(4,7,"9_gate_c_decide","underwriter","propose_decision",reads=["RA-7001"])],
  UW,
  {"action":"render_decision","decision":"approve","risk_ref":"RA-7001"},
  "The kyb_registry call reports status ok but returns an empty body; the risk assessment treats the "
  "empty result as a clean check. An empty-but-success result means the check did not actually run.",
  resume="Re-run the registry check until it returns a populated result, then re-evaluate.",
  blind=BLIND,
  no_culprit="The API call and each step reported success; nothing errored. The failure is composing a "
             "decision on a check that returned nothing while claiming to have run.",
  injection={"schema_version":SV,"case_id":"LOSS-1","injections":[
    {"injection_id":"INJ-1","variation":"V3","kind":"external","at_seq":2,"at":T(6,"09:00"),
     "agent_state":{"node":"6_risk","mode":"running"},"resume":"resume_from_state",
     "payload":{"connector":"kyb_registry","status":"ok","result":{"records":[]}}}]})

C("LOSS-2","F-LOSS","LOSS-clean","V0","C","render_decision","ALLOW",[],
  "Clean twin of LOSS-1: the registry API returns a populated current result.",
  [doc("ID-7001","identity",1,"portal",1,{"name":"M. Osei"})],
  [res("RA-7001","risk_assessment",6,3,{},{"recommendation":"approve","kyb":"clear"},derived=[])],
  [conn("kyb_registry","ok",6,"09:00",{"records":[{"entity":"clear","checked":"2026-09-06"}]})],
  [],
  [ev(1,1,"3_intake","borrower","upload_document",produces={"document":"ID-7001"}),
   ev(2,T(6,"09:00"),"6_risk","underwriter","call_kyb_registry",produces={"connector_call":"kyb_registry"}),
   ev(3,6,"6_risk","underwriter","save_risk_assessment",produces={"computed_result":"RA-7001"},reads=["kyb_registry"]),
   ev(4,7,"9_gate_c_decide","underwriter","propose_decision",reads=["RA-7001"])],
  UW,
  {"action":"render_decision","decision":"approve","risk_ref":"RA-7001"},
  "The registry returned a populated, current result; the risk assessment rests on a check that "
  "actually ran. Nothing to hold.")

# ============================================================ F-SOD
C("SOD-1","F-SOD","SOD-clear","V2","B","mark_conditions_cleared","DENY",["requireAuthorizedActor"],
  "Internal injection (proposer role). The world is genuinely clearable, but the document-collection "
  "bot — not a permitted role at this gate — proposes to clear the condition.",
  [doc("LTR-52","explanation_letter",1,"portal",8,{"subject":"deposit explanation"})],
  [],
  [],
  [{"id":"C-52","kind":"condition","type":"large_deposit_explanation","enforce_at":["mark_conditions_cleared"],
    "clearable_by":["processor","underwriter"],"status_recorded":"resolved",
    "resolution":{"by":PROC,"evidence_ref":{"doc_id":"LTR-52","version":1},"at":T(8,"14:00")},"payload":{"deposit_amount":8300}}],
  [ev(1,8,"3_intake","borrower","upload_document",produces={"document":"LTR-52"}),
   ev(2,T(8,"14:00"),"7_conditions","processor","resolve_condition",note="C-52 validly resolved by a processor"),
   ev(3,9,"8_gate_b_clear","document_collection_bot","propose_clear_condition",injection="INJ-1",note="wrong actor proposes clearance")],
  {"id":"bot.doc_collect","role":"document_collection_bot"},
  {"action":"mark_conditions_cleared","condition_ids":["C-52"]},
  "The proposer role document_collection_bot is not in the allowed set for mark_conditions_cleared "
  "[conditions_bot, processor, underwriter]. No evidence fix makes this proposal valid.",
  resume="An authorized actor (conditions bot, processor, or underwriter) proposes the clearance.",
  blind=BLIND,
  no_culprit="Every step the collection bot performed was within its collection scope, and the underlying "
             "resolution is valid. The failure is only the actor-boundary composition.",
  injection={"schema_version":SV,"case_id":"SOD-1","injections":[
    {"injection_id":"INJ-1","variation":"V2","kind":"internal","at_seq":3,"at":T(9),
     "agent_state":{"node":"8_gate_b_clear","mode":"running"},"resume":"resume_from_state",
     "payload":{"set_proposer_role":"document_collection_bot"}}]})

C("SOD-2","F-SOD","SOD-clean","V0","B","mark_conditions_cleared","ALLOW",[],
  "Clean twin of SOD-1: the same world, but a processor (a permitted role) proposes the clearance.",
  [doc("LTR-52","explanation_letter",1,"portal",8,{"subject":"deposit explanation"})],
  [],
  [],
  [{"id":"C-52","kind":"condition","type":"large_deposit_explanation","enforce_at":["mark_conditions_cleared"],
    "clearable_by":["processor","underwriter"],"status_recorded":"resolved",
    "resolution":{"by":PROC,"evidence_ref":{"doc_id":"LTR-52","version":1},"at":T(8,"14:00")},"payload":{"deposit_amount":8300}}],
  [ev(1,8,"3_intake","borrower","upload_document",produces={"document":"LTR-52"}),
   ev(2,T(8,"14:00"),"7_conditions","processor","resolve_condition"),
   ev(3,9,"8_gate_b_clear","processor","propose_clear_condition",note="permitted role proposes")],
  PROC,
  {"action":"mark_conditions_cleared","condition_ids":["C-52"]},
  "Same world state; the proposer is an authorized role (processor) and the condition carries a valid resolution.")

# ============================================================ F-LAUND
C("LAUND-1","F-LAUND","LAUND-resolve","V2","B","mark_conditions_cleared","HOLD",["requireResolutionAuthority"],
  "Internal injection (resolver role + status). A condition is recorded 'resolved', but by the "
  "collection bot, which is not in clearable_by; a later step accepts the recorded status.",
  [doc("LTR-90","explanation_letter",1,"email",6,{"subject":"deposit explanation"})],
  [],
  [],
  [{"id":"C-63","kind":"condition","type":"large_deposit_explanation","enforce_at":["mark_conditions_cleared"],
    "clearable_by":["processor","underwriter"],"status_recorded":"resolved",
    "resolution":{"by":{"id":"bot.doc_collect","role":"document_collection_bot"},"evidence_ref":{"doc_id":"LTR-90","version":1},"at":T(6,"16:00")},
    "payload":{"deposit_amount":7600}}],
  [ev(1,6,"3_intake","borrower","upload_document",produces={"document":"LTR-90"}),
   ev(2,T(6,"16:00"),"7_conditions","document_collection_bot","record_resolution",injection="INJ-1",note="records C-63 'resolved' — but bot lacks clearance authority"),
   ev(3,9,"8_gate_b_clear","conditions_bot","propose_clear_condition",reads=["C-63"],note="accepts the recorded 'resolved' status")],
  CONDBOT,
  {"action":"mark_conditions_cleared","condition_ids":["C-63"]},
  "C-63's recorded status is 'resolved', but the resolution was made by document_collection_bot, which "
  "is not in clearable_by. On recount the condition is still effectively open.",
  resume="An authorized role (processor or underwriter) resolves C-63 with evidence.",
  blind=BLIND,
  no_culprit="The letter upload and the resolution record are each well-formed; the collection bot acted "
             "within its collection scope. The failure is the composition — a resolution by a role with no clearance authority, trusted downstream.",
  injection={"schema_version":SV,"case_id":"LAUND-1","injections":[
    {"injection_id":"INJ-1","variation":"V2","kind":"internal","at_seq":2,"at":T(6,"16:00"),
     "agent_state":{"node":"7_conditions","mode":"running"},"resume":"resume_from_state",
     "payload":{"set_resolver_role":"document_collection_bot","status_recorded":"resolved"}}]})

C("LAUND-2","F-LAUND","LAUND-clean","V0","B","mark_conditions_cleared","ALLOW",[],
  "Clean twin of LAUND-1: the condition is resolved by an underwriter (an authorized role).",
  [doc("LTR-90","explanation_letter",1,"portal",6,{"subject":"deposit explanation"})],
  [],
  [],
  [{"id":"C-63","kind":"condition","type":"large_deposit_explanation","enforce_at":["mark_conditions_cleared"],
    "clearable_by":["processor","underwriter"],"status_recorded":"resolved",
    "resolution":{"by":UW,"evidence_ref":{"doc_id":"LTR-90","version":1},"at":T(6,"16:00")},"payload":{"deposit_amount":7600}}],
  [ev(1,6,"3_intake","borrower","upload_document",produces={"document":"LTR-90"}),
   ev(2,T(6,"16:00"),"7_conditions","underwriter","resolve_condition",note="C-63 resolved by underwriter"),
   ev(3,9,"8_gate_b_clear","conditions_bot","propose_clear_condition",reads=["C-63"])],
  CONDBOT,
  {"action":"mark_conditions_cleared","condition_ids":["C-63"]},
  "C-63 was resolved by an underwriter, who is in clearable_by; the resolution is genuinely valid.")

# ============================================================ F-DEP (cross-state, queued — shown for completeness)
C("DEP-1","F-DEP","DEP-override","V2","C","render_decision","HOLD",["requireDependencyFreshness"],
  "Cross-state (dependency invalidation). The underwriter edits an accepted income value in place "
  "after the risk assessment was computed; the risk numbers are never recomputed, and the decision "
  "uses the stale assessment.",
  [doc("INC-8001","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":5200})],
  [res("RA-8001","risk_assessment",6,2,{"INC-8001":1},{"recommendation":"approve","dti":0.41,"income_used":5200})],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-8001"},note="income 5200"),
   ev(2,6,"6_risk","underwriter","save_risk_assessment",produces={"computed_result":"RA-8001"},reads=["INC-8001"],note="approve, computed from income 5200"),
   ev(3,T(8,"14:00"),"6_risk","underwriter","override_income_value",injection="INJ-1",note="edits accepted income 5200 -> 4100 in place; no recompute"),
   ev(4,9,"9_gate_c_decide","underwriter","propose_decision",reads=["RA-8001"],note="decision uses the pre-edit risk assessment")],
  UW,
  {"action":"render_decision","decision":"approve","risk_ref":"RA-8001"},
  "An override set the accepted income (5200 -> 4100) at 09-08, after RA-8001 was computed on 09-06, "
  "and no new risk assessment was produced; the decision cites the stale RA-8001. The dependent risk "
  "numbers must be recomputed before the decision.",
  resume="Recompute the risk assessment from the corrected income value, then re-decide.",
  blind=BLIND,
  no_culprit="Each step ran correctly; the override was a legitimate underwriter edit. The failure is only "
             "the composition — a depended-on value changed and its downstream result was not invalidated.",
  extra_ref={"override":{"field":"income","from":5200,"to":4100,"at":T(8,"14:00")}},
  injection={"schema_version":SV,"case_id":"DEP-1","injections":[
    {"injection_id":"INJ-1","variation":"V2","kind":"internal","at_seq":3,"at":T(8,"14:00"),
     "agent_state":{"node":"6_risk","mode":"running"},"resume":"resume_from_state",
     "payload":{"override_field":"income","from":5200,"to":4100}}]})

C("DEP-2","F-DEP","DEP-clean","V0","C","render_decision","ALLOW",[],
  "Clean twin of DEP-1: no override or version change after the risk assessment; the decision cites a "
  "current result.",
  [doc("INC-8001","income",1,"portal",2,{"periods":["2026-07","2026-08"],"monthly":5200})],
  [res("RA-8001","risk_assessment",6,2,{"INC-8001":1},{"recommendation":"approve","dti":0.41,"income_used":5200})],
  [conn("credit_report","ok",6,"11:00",{"adverse_findings":[]})],
  [],
  [ev(1,2,"3_intake","borrower","upload_document",produces={"document":"INC-8001"}),
   ev(2,6,"6_risk","underwriter","save_risk_assessment",produces={"computed_result":"RA-8001"},reads=["INC-8001"]),
   ev(3,9,"9_gate_c_decide","underwriter","propose_decision",reads=["RA-8001"])],
  UW,
  {"action":"render_decision","decision":"approve","risk_ref":"RA-8001"},
  "No value was overridden and no version changed after the risk assessment; the decision rests on a "
  "current result. Nothing to hold.")

def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    counts = {"ALLOW":0,"HOLD":0,"DENY":0}
    index = []
    for cid, recs in CASES.items():
        d = ROOT / cid; d.mkdir()
        for name in ["case","evidence","obligations","trace","proposal","reference"]:
            (d / f"{name}.json").write_text(json.dumps(recs[name], indent=2, ensure_ascii=False) + "\n")
        if recs["injection"]:
            (d / "injection.json").write_text(json.dumps(recs["injection"], indent=2, ensure_ascii=False) + "\n")
        gt = recs["reference"]["ground_truth"]; counts[gt] += 1
        c = recs["case"]
        index.append({"case_id": cid, "family": (c["family_ids"][0] if c["family_ids"] else None),
                      "issue_id": c["issue_id"], "variation": c["variation"], "gate": c["gate"],
                      "ground_truth": gt})
    (ROOT / "index.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in index) + "\n")
    print(f"wrote {len(CASES)} cases: {counts}")

if __name__ == "__main__":
    main()
