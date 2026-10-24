from typing import Any, Optional

import httpx

from .config import Settings


class AgentsUnavailableError(RuntimeError):
    pass


class AgentsClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.agents_base_url

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.base_url}{path}", json=payload)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AgentsUnavailableError(f"Fetch agents unavailable: {error}") from error

    async def plan(self, raw_request: str, user_id: str, session_id: str,
                   profile: Optional[dict[str, Any]] = None,
                   wardrobe: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        return await self._post("/plan", {
            "raw_request": raw_request,
            "user_id": user_id,
            "session_id": session_id,
            "profile": profile,
            "wardrobe": wardrobe or [],
        })

    async def modify(self, session_id: str, user_id: str, message: str,
                     target_outfit_id: Optional[str] = None,
                     profile: Optional[dict[str, Any]] = None,
                     wardrobe: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        return await self._post("/modify", {
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            "target_outfit_id": target_outfit_id,
            "profile": profile,
            "wardrobe": wardrobe,
        })

