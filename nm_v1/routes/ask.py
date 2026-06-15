from fastapi import APIRouter, HTTPException

from nm_v1.clients.gemini import GeminiError, GeminiNotConfigured, chat_with_tools
from nm_v1.models import AskRequest, AskResponse
from nm_v1.services.ask import (
    SYSTEM_PROMPT,
    TOOL_DECLARATIONS,
    AskContext,
    execute_tool,
)

router = APIRouter(prefix="/v1", tags=["ask"])


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    ctx = AskContext()

    async def executor(name: str, args: dict) -> dict:
        return await execute_tool(name, args, ctx)

    try:
        answer = await chat_with_tools(
            question=req.question,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOL_DECLARATIONS,
            executor=executor,
            history=[m.model_dump() for m in req.history],
        )
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return AskResponse(answer=answer)
