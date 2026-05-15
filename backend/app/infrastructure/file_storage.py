from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredFile:
    storage_backend: str
    storage_path: str
    file_size: int


class LocalFileStorage:
    storage_backend = "local"

    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir)

    def save(
        self,
        workspace_id: str,
        file_id: str,
        original_name: str,
        content: bytes,
    ) -> StoredFile:
        workspace_dir = self.root_dir / workspace_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(original_name).name
        path = workspace_dir / f"{file_id}_{safe_name}"
        path.write_bytes(content)
        return StoredFile(
            storage_backend=self.storage_backend,
            storage_path=str(path),
            file_size=len(content),
        )
