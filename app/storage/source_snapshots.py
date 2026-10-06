"""Content-addressed S3-compatible storage for immutable source response bytes.

The database copy remains present and is always available as a read fallback.
Objects are addressed by SHA-256 of the uncompressed source bytes; failed or
interrupted database commits can leave harmless, reusable orphan objects.
"""
from __future__ import annotations

import hashlib
import gzip
import logging
import os
import zlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("leiaberta.source_snapshots")


class SnapshotObjectError(RuntimeError):
    """Object storage could not return bytes matching the recorded checksum."""


@dataclass(frozen=True)
class SnapshotObjectRef:
    backend: str
    object_key: str
    size_bytes: int
    stored_size_bytes: int
    created: bool = field(compare=False)


class SourceSnapshotObjectStore:
    def __init__(self, client: Any, bucket: str, *, prefix: str = "source-snapshots",
                 endpoint_identity: str | None = None) -> None:
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_identity = endpoint_identity

    @classmethod
    def from_env(cls) -> SourceSnapshotObjectStore | None:
        names = {
            "endpoint": "SOURCE_SNAPSHOT_S3_ENDPOINT",
            "access_key": "SOURCE_SNAPSHOT_S3_ACCESS_KEY_ID",
            "secret_key": "SOURCE_SNAPSHOT_S3_SECRET_ACCESS_KEY",
            "region": "SOURCE_SNAPSHOT_S3_REGION",
            "bucket": "SOURCE_SNAPSHOT_S3_BUCKET",
        }
        values = {key: os.getenv(name, "").strip() for key, name in names.items()}
        if not any(values.values()):
            return None
        missing = [names[key] for key, value in values.items() if not value]
        if missing:
            raise ValueError("Incomplete source snapshot object-store configuration: " + ", ".join(missing))
        endpoint = values["endpoint"]
        parsed_endpoint = urlsplit(endpoint)
        if parsed_endpoint.scheme not in {"https", "http"} or not parsed_endpoint.hostname:
            raise ValueError("SOURCE_SNAPSHOT_S3_ENDPOINT must be an http(s) URL")
        addressing_style = os.getenv("SOURCE_SNAPSHOT_S3_ADDRESSING_STYLE", "path").strip().lower()
        if addressing_style not in {"path", "virtual"}:
            raise ValueError("SOURCE_SNAPSHOT_S3_ADDRESSING_STYLE must be path or virtual")

        # Import lazily: installations using database-only snapshots do not
        # need to initialize an S3 client or contact the object store.
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=values["access_key"],
            aws_secret_access_key=values["secret_key"],
            region_name=values["region"],
            # The migration runner applies its own bounded retry policy around
            # an entire put/read/verify operation, so each SDK request is single-shot.
            config=Config(s3={"addressing_style": addressing_style},
                          retries={"mode": "standard", "total_max_attempts": 1}),
        )
        host = parsed_endpoint.hostname.lower()
        if parsed_endpoint.port:
            host = f"{host}:{parsed_endpoint.port}"
        identity = f"{parsed_endpoint.scheme}://{host}{parsed_endpoint.path.rstrip('/')}"
        return cls(client, values["bucket"], prefix=os.getenv("SOURCE_SNAPSHOT_S3_PREFIX", "source-snapshots"),
                   endpoint_identity=identity)

    def key_for(self, sha256: str) -> str:
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            raise ValueError("sha256 must be a lowercase 64-character hexadecimal digest")
        key = f"sha256/{sha256[:2]}/{sha256}"
        return f"{self.prefix}/{key}" if self.prefix else key

    @staticmethod
    def _missing_object(error: Exception) -> bool:
        response = getattr(error, "response", {}) or {}
        details = response.get("Error", {}) if isinstance(response, dict) else {}
        code = str(details.get("Code", ""))
        status = (response.get("ResponseMetadata", {}) or {}).get("HTTPStatusCode")
        return code in {"404", "NoSuchKey", "NotFound"} or status == 404

    def read_verified(self, object_key: str, expected_sha256: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise SnapshotObjectError(f"Could not read source snapshot object {object_key}") from exc
        body = response["Body"]
        try:
            stored_bytes = body.read()
        finally:
            close = getattr(body, "close", None)
            if close:
                close()
        content_encoding = str(response.get("ContentEncoding", "")).lower()
        try:
            payload = gzip.decompress(stored_bytes) if any(
                item.strip() == "gzip" for item in content_encoding.split(",")
            ) else stored_bytes
        except (OSError, EOFError, zlib.error) as exc:
            raise SnapshotObjectError(f"Could not decompress source snapshot object {object_key}") from exc
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected_sha256:
            raise SnapshotObjectError(
                f"Source snapshot checksum mismatch for {object_key}: expected {expected_sha256}, got {actual}"
            )
        return payload

    @staticmethod
    def _compressible(content_type: str) -> bool:
        mime_type = content_type.split(";", 1)[0].strip().lower()
        return mime_type.startswith("text/") or mime_type in {
            "application/xml", "application/xhtml+xml", "application/json", "application/ld+json",
        }

    def put_verified(self, payload: bytes, expected_sha256: str, *,
                     content_type: str = "application/octet-stream") -> SnapshotObjectRef:
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected_sha256:
            raise SnapshotObjectError(
                f"Database source snapshot checksum mismatch: expected {expected_sha256}, got {actual}"
            )
        key = self.key_for(expected_sha256)
        compress = self._compressible(content_type)
        stored_payload = gzip.compress(payload, compresslevel=6, mtime=0) if compress else payload
        created = False
        try:
            head_response = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if not self._missing_object(exc):
                raise SnapshotObjectError(f"Could not inspect source snapshot object {key}") from exc
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=stored_payload,
                ContentType=content_type or "application/octet-stream",
                **({"ContentEncoding": "gzip"} if compress else {}),
                Metadata={
                    "sha256": expected_sha256,
                    "size-bytes": str(len(payload)),
                    "compression": "gzip" if compress else "none",
                },
            )
            created = True

        # Verify actual object bytes rather than trusting user metadata, ETag
        # (which is not always a content MD5), or a successful PUT response.
        stored = self.read_verified(key, expected_sha256)
        if len(stored) != len(payload):
            raise SnapshotObjectError(f"Source snapshot size mismatch for {key}")
        try:
            head_response = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise SnapshotObjectError(f"Could not inspect verified source snapshot object {key}") from exc
        stored_size_bytes = int(head_response.get("ContentLength", -1))
        if stored_size_bytes < 0:
            raise SnapshotObjectError(f"Source snapshot object size is unavailable for {key}")
        return SnapshotObjectRef(backend="s3", object_key=key, size_bytes=len(stored),
                                 stored_size_bytes=stored_size_bytes, created=created)


def read_source_snapshot(snapshot, store: SourceSnapshotObjectStore | None = None) -> bytes:
    """Prefer a verified external object, falling back to the retained DB copy."""
    if snapshot.storage_backend == "s3" and snapshot.object_key:
        try:
            active_store = store or SourceSnapshotObjectStore.from_env()
            if active_store is None:
                raise SnapshotObjectError("No source snapshot object-store configuration is available")
            return active_store.read_verified(snapshot.object_key, snapshot.checksum)
        except Exception as exc:
            # Keep fallback observable without printing repeated tracebacks or
            # endpoint details when an optional object service is unavailable.
            logger.warning("source_snapshot_object_read_failed id=%s error_type=%s; using retained database bytes",
                           snapshot.id, type(exc).__name__)

    raw_body = snapshot.raw_body
    if raw_body is None:
        raise SnapshotObjectError(f"Source snapshot {snapshot.id} has neither readable object storage nor DB bytes")
    raw_body = bytes(raw_body)
    actual = hashlib.sha256(raw_body).hexdigest()
    if actual != snapshot.checksum:
        raise SnapshotObjectError(
            f"Retained database source snapshot checksum mismatch for id={snapshot.id}: "
            f"expected {snapshot.checksum}, got {actual}"
        )
    return raw_body


def archive_snapshot_object(payload: bytes, checksum: str, content_type: str = "application/octet-stream") -> SnapshotObjectRef | None:
    """Upload a new response when configured; no configuration means DB-only."""
    store = SourceSnapshotObjectStore.from_env()
    if store is None:
        return None
    return store.put_verified(payload, checksum, content_type=content_type)
