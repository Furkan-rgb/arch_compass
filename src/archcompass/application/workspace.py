"""Workspace configuration initialization."""

from __future__ import annotations

from pathlib import Path

from archcompass.application.safety import safe_workspace_output_path
from archcompass.configuration import default_config_text
from archcompass.domain.errors import PathValidationError


class WorkspaceConfigurationService:
    def initialize(
        self,
        workspace: Path,
        config_path: Path,
        *,
        allow_external_config: bool = False,
    ) -> list[Path]:
        canonical_workspace = workspace.expanduser().resolve()
        canonical_workspace.mkdir(parents=True, exist_ok=True)
        if allow_external_config:
            target = config_path.expanduser().resolve()
        else:
            requested = config_path.expanduser()
            if requested.is_absolute():
                try:
                    relative = requested.relative_to(canonical_workspace)
                except ValueError as error:
                    raise PathValidationError(
                        "The default configuration path must remain inside the workspace"
                    ) from error
            else:
                relative = requested
            target = safe_workspace_output_path(canonical_workspace, relative)
        if target.exists():
            return []
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(default_config_text(), encoding="utf-8")
        return [target]
