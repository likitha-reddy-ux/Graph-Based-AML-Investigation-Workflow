"""
LLM wrapper for drafting case narratives.

Choose the provider with the LLM_PROVIDER environment variable:
    anthropic  - Claude, needs ANTHROPIC_API_KEY
    gemini     - Google Gemini, needs GEMINI_API_KEY
    template   - no LLM; builds the draft from rules (default, free, runs anywhere)

Optionally set LLM_MODEL to choose a specific model for the provider.
"""

import json
import os
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from prompts import SYSTEM_PROMPT, build_user_prompt

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "gemini": "gemini-2.5-flash",
}


class CaseDraft(BaseModel):
    summary: str
    key_indicators: list[str] = Field(default_factory=list)
    recommended_action: Literal["escalate", "monitor", "close"]
    narrative: str


def provider_name() -> str:
    return os.environ.get("LLM_PROVIDER", "template").lower()


def _call_anthropic(user_prompt: str, model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _call_gemini(user_prompt: str, model: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _parse_draft(text: str) -> CaseDraft:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return CaseDraft.model_validate(json.loads(match.group(0)))


def _template_draft(evidence: dict, signals: dict) -> CaseDraft:
    """Rule-based draft used when no LLM is configured."""
    tx = evidence["transaction"]
    indicators = signals["patterns"] or ["high model risk score"]
    action = "escalate" if signals["priority"] == "high" else "monitor"

    narrative = (
        f"Transaction {tx['tx_id']} (time step {tx['time_step']}) was flagged by the "
        f"GraphSAGE model with a risk score of {tx['risk_score']:.2f}. It received funds "
        f"from {signals['in_degree']} transaction(s) and sent funds to "
        f"{signals['out_degree']} transaction(s). Of its {signals['direct_neighbours']} "
        f"direct counterparties, {signals['flagged_neighbours']} are also flagged as high "
        f"risk and {signals['illicit_neighbours']} carry a known illicit label. Within two "
        f"hops, {signals['second_hop_flagged']} further transactions are flagged. "
        f"Observed patterns: {', '.join(indicators)}. Its own label in the dataset is "
        f"'{tx['label']}'. This draft is based only on graph structure and model scores "
        f"and requires analyst review before any decision."
    )
    summary = (
        f"Transaction {tx['tx_id']} has a {tx['risk_score']:.2f} risk score and "
        f"{signals['flagged_neighbours']} flagged direct counterparties; "
        f"priority {signals['priority']}."
    )
    return CaseDraft(
        summary=summary,
        key_indicators=indicators,
        recommended_action=action,
        narrative=narrative,
    )


def draft_case(evidence: dict, signals: dict) -> CaseDraft:
    provider = provider_name()
    if provider == "template":
        return _template_draft(evidence, signals)

    model = os.environ.get("LLM_MODEL", DEFAULT_MODELS.get(provider, ""))
    payload = json.dumps({"evidence": evidence, "signals": signals}, indent=2)
    user_prompt = build_user_prompt(payload)

    call = {"anthropic": _call_anthropic, "gemini": _call_gemini}.get(provider)
    if call is None:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

    # One retry if the model returns invalid JSON
    for attempt in range(2):
        text = call(user_prompt, model)
        try:
            return _parse_draft(text)
        except (ValueError, ValidationError, json.JSONDecodeError) as err:
            if attempt == 1:
                raise RuntimeError(f"Model did not return a valid draft: {err}") from err
            user_prompt += "\n\nYour last reply was not valid JSON. Reply with the JSON object only."
