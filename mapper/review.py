"""Reviewer decisions, stored per company on the server.

Decisions are append-only (history). The latest decision per duty element is the current one.
Each decision stores the fingerprint of the proposal it was made on; if a later run proposes
something different (status or cited sources changed), the decision is shown as "Re-review needed".
"""
from datetime import datetime, timezone

DECISIONS = {"confirmed": "Confirmed", "rejected": "Rejected", "needs_clarification": "Needs clarification"}


def load(company):
    return company.store.load_decisions()


def add(company, run_result, payload):
    """Validate and append one decision. The fingerprint is taken from the server-side result, not the client."""
    decision = payload.get("decision")
    reviewer = (payload.get("reviewer") or "").strip()
    comment = (payload.get("comment") or "").strip()
    if decision not in DECISIONS:
        raise ValueError("decision must be one of: " + ", ".join(DECISIONS))
    if not reviewer or len(reviewer) > 100:
        raise ValueError("reviewer name is required (max 100 characters)")
    if len(comment) > 2000:
        raise ValueError("comment is too long (max 2000 characters)")
    el = None
    for du in run_result["duties"]:
        if du["duty_id"] == payload.get("duty_id"):
            el = next((e for e in du.get("elements", []) if e["id"] == payload.get("element_id")), None)
    if el is None:
        raise ValueError("unknown duty or element for this run")
    rec = {"duty_id": payload["duty_id"], "element_id": payload["element_id"], "decision": decision,
           "comment": comment, "reviewer": reviewer,
           "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "run_id": run_result["run_id"], "fingerprint": el["fingerprint"],
           "proposal": {"policy_status": el["policy_status"], "implementation": el["implementation"]["state"],
                        "effectiveness": el["effectiveness"]["state"]}}
    company.store.append_decision(rec)
    return rec


def current(decisions, duty_id, element_id, fingerprint):
    """Latest decision for an element, with 'stale' when the proposal changed since it was made."""
    hist = [d for d in decisions if d["duty_id"] == duty_id and d["element_id"] == element_id]
    if not hist:
        return None, []
    last = dict(hist[-1])
    last["stale"] = last["fingerprint"] != fingerprint
    last["label"] = DECISIONS[last["decision"]]
    return last, hist
