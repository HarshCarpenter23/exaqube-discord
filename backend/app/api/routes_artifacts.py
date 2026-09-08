"""Artifact download endpoint. Serves generated files with the correct content
type and a download disposition. Unknown or malformed ids return a 404 envelope.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import NotFound
from app.artifacts import ArtifactStore
from app.config import get_settings

router = APIRouter(prefix="/api")

_store = ArtifactStore(get_settings().artifact_dir)


def get_artifact_store() -> ArtifactStore:
    """Shared store instance (used by this router and the chat loop)."""
    return _store


@router.get("/artifacts/{artifact_id}")
async def download_artifact(artifact_id: str):
    info = _store.get(artifact_id)
    if info is None:
        raise NotFound("Artifact not found.")
    return FileResponse(
        _store.path_for(info.id),
        media_type=info.content_type,
        filename=info.filename,
    )
