"""Artifact store for downloadable files (Excel, PowerPoint, ...).

Files are written to a temp path and atomically moved into place, so a partial
or cancelled write is never served. Each file is stored under a random id with a
small sidecar recording its real filename and content type, which the download
endpoint uses.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def _sanitize_filename(name: str) -> str:
    """Strip anything that could enable path traversal or odd headers."""
    return _SAFE_NAME.sub("_", name).strip() or "artifact"


@dataclass
class ArtifactInfo:
    id: str
    filename: str
    content_type: str

    @property
    def url(self) -> str:
        return f"/api/artifacts/{self.id}"

    def as_dict(self) -> dict:
        return {
            "artifact_id": self.id,
            "filename": self.filename,
            "content_type": self.content_type,
            "url": self.url,
        }


class ArtifactStore:
    def __init__(self, base_dir: str):
        self._base = base_dir
        self._tmp = os.path.join(base_dir, "tmp")
        os.makedirs(self._tmp, exist_ok=True)

    def write_bytes(self, data: bytes, filename: str, content_type: str) -> ArtifactInfo:
        artifact_id = uuid.uuid4().hex
        info = ArtifactInfo(artifact_id, _sanitize_filename(filename), content_type)

        tmp_path = os.path.join(self._tmp, artifact_id)
        with open(tmp_path, "wb") as fh:
            fh.write(data)
        os.replace(tmp_path, self._path(artifact_id))  # atomic

        with open(self._meta_path(artifact_id), "w", encoding="utf-8") as fh:
            json.dump({"filename": info.filename, "content_type": info.content_type}, fh)
        return info

    def get(self, artifact_id: str) -> ArtifactInfo | None:
        """Look up a stored artifact. Returns None for unknown or malformed ids."""
        if not re.fullmatch(r"[0-9a-f]{32}", artifact_id):
            return None
        if not os.path.exists(self._path(artifact_id)):
            return None
        with open(self._meta_path(artifact_id), encoding="utf-8") as fh:
            meta = json.load(fh)
        return ArtifactInfo(artifact_id, meta["filename"], meta["content_type"])

    def path_for(self, artifact_id: str) -> str:
        return self._path(artifact_id)

    def _path(self, artifact_id: str) -> str:
        return os.path.join(self._base, artifact_id)

    def _meta_path(self, artifact_id: str) -> str:
        return os.path.join(self._base, f"{artifact_id}.json")
