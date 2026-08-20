from typing import Any, Dict
import httpx


class HonchoClient:
    """
    Placeholder client shell for Honcho REST integration.
    Reads raw context from self-hosted Honcho instance without modifying Honcho.
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def get_session_context(
        self, workspace_id: str, session_id: str, tokens: int = 4000
    ) -> Dict[str, Any]:
        """Fetch raw session context from Honcho."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v3/workspaces/{workspace_id}/sessions/{session_id}/context",
                headers=self.headers,
                params={"tokens": tokens},
            )
            resp.raise_for_status()
            return resp.json()
