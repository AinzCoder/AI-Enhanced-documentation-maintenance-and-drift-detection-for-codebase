"""Authentication and repository workspace authorization."""

import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import jwt
import requests
from fastapi import Header, HTTPException


_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
_ID = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class Access:
    mode: str
    issuer: str = ""
    subject: str = ""


@dataclass(frozen=True)
class Workspace:
    repository_id: str | None
    path: Path


def _https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _configuration() -> tuple[str, str, list[str], Path, Path]:
    issuer = os.environ.get("DOCGUARD_OIDC_ISSUER", "")
    audience = os.environ.get("DOCGUARD_OIDC_AUDIENCE", "")
    algorithms = os.environ.get("DOCGUARD_OIDC_ALGORITHMS", "").split(",")
    algorithms = [item.strip() for item in algorithms if item.strip()]
    root = os.environ.get("DOCGUARD_WORKSPACE_ROOT", "")
    database = os.environ.get("DOCGUARD_WORKSPACE_DATABASE", "")
    if (
        not _https_url(issuer)
        or not audience
        or not algorithms
        or not set(algorithms) <= _ALGORITHMS
        or not root
        or not database
        or not Path(root).is_absolute()
        or not Path(root).is_dir()
        or not Path(database).is_absolute()
        or not Path(database).parent.is_dir()
        or Path(root).is_symlink()
    ):
        raise HTTPException(503, "Hosted security configuration is incomplete.")
    return issuer, audience, algorithms, Path(root).resolve(), Path(database)


def _get_json(url: str) -> dict:
    try:
        with requests.get(url, timeout=5, allow_redirects=False, stream=True) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise requests.RequestException("Unexpected status")
            data = bytearray()
            for chunk in response.iter_content(8192):
                data.extend(chunk)
                if len(data) > 1024 * 1024:
                    raise ValueError("OIDC response is too large")
            import json
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("OIDC response is not an object")
            return result
    except (requests.RequestException, ValueError) as error:
        raise HTTPException(503, "Identity provider is unavailable.") from error


def authenticate(authorization: str | None = Header(default=None)) -> Access:
    mode = os.environ.get("DOCGUARD_MODE", "")
    if mode == "local":
        return Access("local")
    if mode != "hosted":
        raise HTTPException(503, "DocGuard mode is not configured.")
    issuer, audience, algorithms, _, _ = _configuration()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer authentication is required.", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:]
    if not token or len(token) > 16384:
        raise HTTPException(401, "Invalid access token.")
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in algorithms or not isinstance(kid, str) or not kid:
            raise jwt.InvalidTokenError("Invalid token header")
        metadata = _get_json(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
        jwks_uri = metadata.get("jwks_uri")
        allowed_hosts = {
            host.strip().lower()
            for host in os.environ.get("DOCGUARD_OIDC_JWKS_HOSTS", "").split(",")
            if host.strip()
        }
        allowed_hosts.add(urlsplit(issuer).hostname)
        if (
            metadata.get("issuer") != issuer
            or not isinstance(jwks_uri, str)
            or not _https_url(jwks_uri)
            or urlsplit(jwks_uri).hostname not in allowed_hosts
        ):
            raise HTTPException(503, "Identity provider configuration is invalid.")
        jwks = _get_json(jwks_uri)
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise HTTPException(503, "Identity provider configuration is invalid.")
        matches = [
            item for item in keys if isinstance(item, dict)
            and item.get("kid") == kid
            and item.get("use", "sig") == "sig"
            and item.get("alg", algorithm) == algorithm
        ]
        if len(matches) != 1:
            raise jwt.InvalidTokenError("Signing key not found")
        key = jwt.PyJWK.from_dict(matches[0], algorithm=algorithm).key
        claims = jwt.decode(
            token, key, algorithms=algorithms, audience=audience, issuer=issuer,
            options={"require": ["iss", "sub", "aud", "exp"]},
        )
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise jwt.InvalidTokenError("Invalid subject")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(401, "Invalid access token.", headers={"WWW-Authenticate": "Bearer"}) from error
    return Access("hosted", issuer, subject)


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS workspaces (
        repository_id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
        expires_at REAL NOT NULL, display_name TEXT NOT NULL)"""
    )
    return connection


def create_workspace(access: Access, expires_at: datetime, display_name: str) -> str:
    """Reserve metadata for trusted provisioning code; not exposed over HTTP."""
    if access.mode != "hosted" or expires_at.tzinfo is None:
        raise ValueError("Hosted owner and timezone-aware expiry are required.")
    _, _, _, _, database = _configuration()
    repository_id = uuid.uuid4().hex
    with _connect(database) as connection:
        connection.execute(
            "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?)",
            (repository_id, access.issuer, access.subject, expires_at.timestamp(), display_name),
        )
    return repository_id


def resolve_repository(access: Access, repository_path: str | None, repository_id: str | None) -> Workspace:
    if access.mode == "local":
        if not repository_path:
            raise HTTPException(400, "A local repository path is required.")
        return Workspace(None, Path(repository_path).expanduser())
    if repository_path is not None or not repository_id or not _ID.fullmatch(repository_id):
        raise HTTPException(400, "A repository ID is required; filesystem paths are disabled.")
    _, _, _, root, database = _configuration()
    with _connect(database) as connection:
        row = connection.execute(
            "SELECT expires_at FROM workspaces WHERE repository_id = ? AND issuer = ? AND subject = ?",
            (repository_id, access.issuer, access.subject),
        ).fetchone()
    path = root / repository_id
    if (
        row is None or row["expires_at"] <= datetime.now(timezone.utc).timestamp()
        or path.is_symlink() or not path.is_dir() or path.resolve().parent != root
    ):
        raise HTTPException(404, "Repository workspace was not found.")
    return Workspace(repository_id, path)


def list_workspaces(access: Access) -> list[dict]:
    _, _, _, _, database = _configuration()
    with _connect(database) as connection:
        rows = connection.execute(
            "SELECT repository_id, display_name FROM workspaces WHERE issuer = ? AND subject = ? AND expires_at > ?",
            (access.issuer, access.subject, datetime.now(timezone.utc).timestamp()),
        ).fetchall()
    result = []
    for row in rows:
        try:
            resolve_repository(access, None, row["repository_id"])
        except HTTPException as error:
            if error.status_code == 404:
                continue
            raise
        result.append({"id": row["repository_id"], "name": row["display_name"]})
    return result
