"""Internal import services. No production quota provider is currently available."""

import os
import re
import signal
import subprocess
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from app.security import Access
from repository.github_url import validate_github_repository_url
from repository.safe_zip import ArchiveLimits, extract_validated_zip
from repository.workspace_provisioner import StagingWorkspace, WorkspaceProvisioner


class ImportFailed(RuntimeError):
    pass


class ImportBusy(ImportFailed):
    pass


_IMPORT_SLOTS = threading.BoundedSemaphore(2)
_ID = re.compile(r"[0-9a-f]{32}\Z")


def _clone(url: str, destination: Path, timeout: int) -> None:
    if os.name != "posix":
        raise ImportFailed("Git import requires a supported isolated worker.")
    environment = {
        "PATH": os.defpath,
        "HOME": str(destination.parent),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_ASKPASS": "",
        "LC_ALL": "C",
    }
    command = [
        "git", "-c", "core.hooksPath=/dev/null", "-c", "http.followRedirects=false",
        "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
        "-c", "submodule.recurse=false", "clone", "--no-recurse-submodules",
        "--depth", "2", "--", url, str(destination),
    ]
    try:
        process = subprocess.Popen(
            command, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            result = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ImportFailed("Git clone timed out.") from error
    except OSError as error:
        raise ImportFailed("Git clone could not be started.") from error
    if result:
        raise ImportFailed("Git clone failed.")


class IngestionService:
    def __init__(
        self,
        provisioner: WorkspaceProvisioner,
        *,
        upload_limit: int,
        archive_limits: ArchiveLimits,
        clone_timeout: int = 120,
    ):
        if upload_limit <= 0 or clone_timeout <= 0:
            raise ValueError("Import limits must be positive.")
        self.provisioner = provisioner
        self.upload_limit = upload_limit
        self.archive_limits = archive_limits
        self.clone_timeout = clone_timeout

    def _allocate(self, owner: Access, expires_at: datetime) -> StagingWorkspace:
        if owner.mode != "hosted" or not owner.issuer or not owner.subject:
            raise ImportFailed("A verified hosted owner is required.")
        if expires_at.tzinfo is None or expires_at.timestamp() <= datetime.now(expires_at.tzinfo).timestamp():
            raise ImportFailed("A future workspace expiration is required.")
        self.provisioner.verify_ready()
        self.provisioner.cleanup_expired()
        self.provisioner.verify_ready()
        workspace = self.provisioner.allocate(owner, expires_at)
        try:
            self.provisioner.verify_ready()
            if not _ID.fullmatch(workspace.repository_id) or workspace.directory.is_symlink() or not workspace.directory.is_dir() or any(workspace.directory.iterdir()):
                raise ImportFailed("Provisioned workspace is invalid.")
        except BaseException:
            self.provisioner.discard(workspace)
            raise
        return workspace

    def _run(self, owner: Access, expires_at: datetime, display_name: str, operation) -> str:
        if not _IMPORT_SLOTS.acquire(blocking=False):
            raise ImportBusy("Import capacity is busy.")
        try:
            workspace = self._allocate(owner, expires_at)
            published = False
            try:
                operation(workspace.directory)
                self.provisioner.verify_ready()
                self.provisioner.publish(workspace, owner, display_name)
                published = True
                return workspace.repository_id
            finally:
                if not published:
                    self.provisioner.discard(workspace)
        finally:
            _IMPORT_SLOTS.release()

    def import_github(self, owner: Access, expires_at: datetime, url: str) -> str:
        validated = validate_github_repository_url(url)
        name = validated.rsplit("/", 1)[-1][:-4]
        return self._run(
            owner, expires_at, name,
            lambda root: _clone(validated, root / "repository", self.clone_timeout),
        )

    def import_zip(self, owner: Access, expires_at: datetime, chunks: Iterable[bytes]) -> str:
        def extract(root: Path) -> None:
            upload = root / "upload.zip"
            destination = root / "repository"
            destination.mkdir()
            size = 0
            with upload.open("xb") as target:
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ImportFailed("Invalid upload data.")
                    size += len(chunk)
                    if size > self.upload_limit:
                        raise ImportFailed("Upload exceeds the size limit.")
                    target.write(chunk)
            with upload.open("rb") as source:
                extract_validated_zip(source, destination, self.archive_limits)
            upload.unlink()

        return self._run(owner, expires_at, "ZIP repository", extract)
