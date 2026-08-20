import re
from typing import Any, Dict


class CortexRouterService:
    """
    Lightweight deterministic source & intent router.
    Decides information source among:
    - HONCHO_MEMORY
    - SYNAPSE_STATE
    - BOTH
    - CURRENT_SESSION
    - NO_RETRIEVAL
    Requires 0 LLM calls.
    """

    def route_query(self, text: str) -> Dict[str, Any]:
        lower_query = text.lower().strip()

        # 1. NO_RETRIEVAL / Short banter e.g. "lol", "hello", "hi", "good morning"
        if re.match(r"^(lol|haha|hey|hello|hi|good\s+(morning|afternoon|evening|night)|thanks|thank\s+you|ok|okay)[.!?]*$", lower_query):
            return {
                "route": "NO_RETRIEVAL",
                "reason": "Short banter or conversational acknowledgement",
                "target": "current_session_only",
            }

        # 2. BOTH e.g. "What did James say he would send me and when?"
        if (
            re.search(r"\b(did|has)\s+\w+\s+(ever\s+)?(send|reply|finish|do|complete)", lower_query)
            or ("remind me what" in lower_query and any(term in lower_query for term in ["i said", "i'd do", "i would do"]))
        ):
            return {
                "route": "BOTH",
                "reason": "Query needs source evidence plus current lifecycle resolution state",
                "target": "honcho_and_synapse",
            }

        if ("what did" in lower_query or "when did" in lower_query) and any(kw in lower_query for kw in ["say", "promise", "agree", "send", "tell"]):
            if any(ref in lower_query for ref in ["follow up", "due", "status", "deadline"]):
                return {
                    "route": "BOTH",
                    "reason": "Query requires historical Honcho recall and dynamic Synapse state",
                    "target": "honcho_and_synapse",
                }

        # 3. SYNAPSE_STATE e.g. "What was I supposed to follow up on?", "What do I need to do today?"
        if any(kw in lower_query for kw in ["follow up", "supposed to", "meant to do", "need to do", "my plans", "commitments", "deadlines", "pending", "open loops"]):
            return {
                "route": "SYNAPSE_STATE",
                "reason": "Query asks directly for dynamic lifecycle expectations / state",
                "target": "synapse_state_only",
            }

        # 4. HONCHO_MEMORY e.g. "What did we talk about last night?", "Do you remember my dog's name?"
        if any(kw in lower_query for kw in ["talk about", "talking about", "remember", "last night", "yesterday", "we discussed", "what was", "what did", "why do you think"]):
            return {
                "route": "HONCHO_MEMORY",
                "reason": "Query requests transcript / background semantic memory recall",
                "target": "honcho_memory_only",
            }

        # Default fallback: CURRENT_SESSION
        return {
            "route": "CURRENT_SESSION",
            "reason": "Default turn handling within active conversation window",
            "target": "current_session",
        }
