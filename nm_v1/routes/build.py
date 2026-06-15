from fastapi import APIRouter, HTTPException

from nm_v1.clients.stable_brain import (
    StableBrainError,
    StableBrainNotConfigured,
    ask_system,
)
from nm_v1.models import BuildRequest, BuildResponse
from nm_v1.services.build import normalize_build_result

router = APIRouter(prefix="/v1", tags=["build"])


@router.post("/build", response_model=BuildResponse)
async def build(req: BuildRequest):
    try:
        result = await ask_system(req.query)
    except StableBrainNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except StableBrainError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return normalize_build_result(result)
