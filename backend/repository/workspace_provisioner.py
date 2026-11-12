"""Contract for an isolated, quota-enforced workspace storage provider."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.security import Access


class ProvisioningUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StagingWorkspace:
    repository_id: str
    directory: Path


class WorkspaceProvisioner(Protocol):
    """Implementations must enforce hard import, owner and aggregate quotas."""

    def verify_ready(self) -> None:
        """Verify quota enforcement and lifecycle recovery; raise if unavailable."""
        ...

    def allocate(self, owner: Access, expires_at: datetime) -> StagingWorkspace:
        """Atomically reserve private, quota-enforced staging for this owner."""
        ...

    def publish(self, workspace: StagingWorkspace, owner: Access, display_name: str) -> None:
        """Atomically publish repository and owner metadata under its opaque ID."""
        ...

    def discard(self, workspace: StagingWorkspace) -> None:
        """Remove staging and release all reservations, or raise on failure."""
        ...

    def cleanup_expired(self) -> None:
        """Reconcile abandoned staging and expired published workspaces safely."""
        ...


class UnavailableProvisioner:
    """Production default until a verified Linux quota provider is implemented."""

    def verify_ready(self) -> None:
        raise ProvisioningUnavailable("Quota-backed workspace provisioning is unavailable.")

    def allocate(self, owner: Access, expires_at: datetime) -> StagingWorkspace:
        self.verify_ready()
        raise AssertionError("unreachable")

    def publish(self, workspace: StagingWorkspace, owner: Access, display_name: str) -> None:
        self.verify_ready()

    def discard(self, workspace: StagingWorkspace) -> None:
        self.verify_ready()

    def cleanup_expired(self) -> None:
        self.verify_ready()
