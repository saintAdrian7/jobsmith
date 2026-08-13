import json

import yaml

from pipeline.llm import LLMError
from pipeline.store import Store

SYSTEM = (
    "You evaluate a job lead against a candidate's ideal employer profile. "
    'Respond with JSON only: {"score": <float 0..1>, "rationale": "<one sentence>"}'
)


def score_leads(store: Store, provider, iep: dict, only_new: bool = True) -> list[dict]:
    """Score unscored leads against the IEP; returns {id, company, score} rows, best first."""
    index = store.read_index("leads")
    rows = []
    for lead_id, entry in index.items():
        if only_new and entry["status"] != "new":
            continue
        lead = store.load_lead(lead_id)
        try:
            result = _ask_with_one_retry(provider, iep, lead)
            lead.score = float(result["score"])
            lead.score_rationale = str(result.get("rationale", ""))
            store.update_lead(lead)
            store.set_lead_status(lead_id, "scored")
            rows.append({"id": lead_id, "company": lead.company, "score": lead.score})
        except (LLMError, KeyError, TypeError, ValueError) as e:
            rows.append({"id": lead_id, "company": lead.company, "score": None, "error": str(e)})
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


def _ask_with_one_retry(provider, iep: dict, lead) -> dict:
    """One scoring call with a single re-ask on failure, per spec."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"PROFILE:\n{yaml.safe_dump(iep)}\nLEAD:\n{json.dumps(lead.to_dict())}",
        },
    ]
    try:
        result = provider.complete(messages, json_mode=True)
        _validate_response(result)
        return result
    except LLMError:
        result = provider.complete(messages, json_mode=True)
        _validate_response(result)
        return result


def _validate_response(result: dict) -> None:
    """Validate response schema; raise LLMError on invalid shape."""
    if not isinstance(result, dict):
        raise LLMError(f"response must be dict, got {type(result).__name__}")
    if "score" not in result:
        raise LLMError("response missing required 'score' field")
    try:
        float(result["score"])
    except (TypeError, ValueError) as e:
        raise LLMError(f"'score' must be numeric: {e}") from e
