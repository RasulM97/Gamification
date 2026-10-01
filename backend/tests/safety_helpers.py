"""Controlled immutable safety evidence for the approval contract gate only."""
import hashlib
import json
from app.incentive_safety.persistence import record


def safety(db, chain, outcome='REQUIRE_REVIEW', revision=1, company='gold-a'):
    evidence={'testControlledContractEvidence':True,'revision':revision}
    fingerprint=hashlib.sha256(json.dumps([chain['candidate'],outcome,evidence],sort_keys=True).encode()).hexdigest()
    result=record(db,company,chain['candidate'],fingerprint=fingerprint,outcome=outcome,
                  findings=[] if outcome=='CLEAR' else [{'type':'CONTRACT_GATE','outcome':outcome}],evidence=evidence)
    db.commit()
    return result
