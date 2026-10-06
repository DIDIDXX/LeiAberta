from __future__ import annotations

import hashlib
import gzip
from io import BytesIO

import pytest

from app.models import SourceSnapshot
from app.storage.source_snapshots import (
    SnapshotObjectError,
    SourceSnapshotObjectStore,
    read_source_snapshot,
)
from scripts.migrate_source_snapshots_to_object_storage import migrate_batch


class FakeClientError(Exception):
    def __init__(self, code="404"):
        self.response = {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": int(code) if code.isdigit() else 500}}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.put_count = 0

    def head_object(self, *, Bucket, Key):
        try:
            obj = self.objects[(Bucket, Key)]
        except KeyError:
            raise FakeClientError()
        return {"ContentLength": len(obj["body"]), "Metadata": obj["metadata"]}

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata, ContentEncoding=None):
        self.put_count += 1
        self.objects[(Bucket, Key)] = {
            "body": bytes(Body), "metadata": dict(Metadata),
            "content_type": ContentType, "content_encoding": ContentEncoding,
        }
        return {"ETag": '"fake"'}

    def get_object(self, *, Bucket, Key):
        try:
            obj = self.objects[(Bucket, Key)]
        except KeyError:
            raise FakeClientError()
        return {"Body": BytesIO(obj["body"]), "ContentType": obj["content_type"],
                "ContentEncoding": obj["content_encoding"]}


def _snapshot(law, body: bytes, **kwargs):
    return SourceSnapshot(
        law_slug=law.slug, source_url="https://example.gov.br/law",
        checksum=hashlib.sha256(body).hexdigest(), raw_format="text/html", raw_body=body,
        **kwargs,
    )


def test_object_store_deduplicates_identical_content_by_sha256():
    client = FakeS3()
    store = SourceSnapshotObjectStore(client, "snapshots", prefix="legal")
    body = b"official source bytes"
    digest = hashlib.sha256(body).hexdigest()

    first = store.put_verified(body, digest, content_type="text/html; charset=utf-8")
    stored = client.objects[("snapshots", first.object_key)]
    second = store.put_verified(body, digest, content_type="text/html; charset=utf-8")

    assert first == second
    assert first.backend == "s3"
    assert first.object_key == f"legal/sha256/{digest[:2]}/{digest}"
    assert first.size_bytes == len(body)
    assert stored["body"] != body
    assert stored["body"] == gzip.compress(body, compresslevel=6, mtime=0)
    assert stored["content_type"] == "text/html; charset=utf-8"
    assert stored["content_encoding"] == "gzip"
    assert stored["metadata"]["sha256"] == digest
    assert store.read_verified(first.object_key, digest) == body
    assert client.put_count == 1


def test_binary_snapshot_is_stored_without_compression():
    client = FakeS3()
    store = SourceSnapshotObjectStore(client, "snapshots")
    body = b"%PDF-1.7\x00\x80binary-content"
    digest = hashlib.sha256(body).hexdigest()

    ref = store.put_verified(body, digest, content_type="application/pdf")
    stored = client.objects[("snapshots", ref.object_key)]

    assert stored["body"] == body
    assert stored["content_encoding"] is None
    assert stored["metadata"]["compression"] == "none"
    assert store.read_verified(ref.object_key, digest) == body


def test_object_store_rejects_source_checksum_mismatch_without_upload():
    client = FakeS3()
    store = SourceSnapshotObjectStore(client, "snapshots")

    with pytest.raises(SnapshotObjectError, match="Database source snapshot checksum mismatch"):
        store.put_verified(b"different bytes", "0" * 64)

    assert client.put_count == 0
    assert client.objects == {}


def test_existing_corrupt_object_is_never_overwritten():
    client = FakeS3()
    store = SourceSnapshotObjectStore(client, "snapshots")
    body = b"the expected legal evidence"
    digest = hashlib.sha256(body).hexdigest()
    key = store.key_for(digest)
    client.objects[("snapshots", key)] = {
        "body": b"corrupt object", "metadata": {"sha256": digest},
        "content_type": "application/octet-stream", "content_encoding": None,
    }

    with pytest.raises(SnapshotObjectError, match="checksum mismatch"):
        store.put_verified(body, digest)

    assert client.put_count == 0
    assert client.objects[("snapshots", key)]["body"] == b"corrupt object"


def test_dual_read_verifies_object_and_falls_back_to_database_copy(db_session, add_law):
    law = add_law()
    body = b"verified retained bytes"
    digest = hashlib.sha256(body).hexdigest()
    client = FakeS3()
    store = SourceSnapshotObjectStore(client, "snapshots")
    ref = store.put_verified(body, digest)
    snapshot = _snapshot(law, body, storage_backend=ref.backend, object_key=ref.object_key)

    assert read_source_snapshot(snapshot, store) == body

    client.objects[("snapshots", ref.object_key)]["body"] = b"corrupt object"
    assert read_source_snapshot(snapshot, store) == body


def test_dual_read_rejects_when_object_and_database_fallback_are_corrupt(db_session, add_law):
    law = add_law()
    body = b"verified source bytes"
    digest = hashlib.sha256(body).hexdigest()
    client = FakeS3()
    store = SourceSnapshotObjectStore(client, "snapshots")
    ref = store.put_verified(body, digest, content_type="text/html")
    snapshot = _snapshot(law, body, storage_backend=ref.backend, object_key=ref.object_key)
    client.objects[("snapshots", ref.object_key)]["body"] = b"corrupt object"
    snapshot.raw_body = b"corrupt database copy"

    with pytest.raises(SnapshotObjectError, match="Retained database source snapshot checksum mismatch"):
        read_source_snapshot(snapshot, store)


def test_snapshot_migration_is_bounded_restartable_and_idempotent(db_session, add_law):
    law = add_law()
    db_session.add(law)
    db_session.flush()
    first_body = b"first source"
    second_body = b"second source"
    first = _snapshot(law, first_body)
    second = _snapshot(law, second_body)
    db_session.add_all([first, second])
    db_session.commit()
    fake_s3 = FakeS3()
    store = SourceSnapshotObjectStore(fake_s3, "snapshots")

    dry_run = migrate_batch(session=db_session, batch_size=1, apply=False)
    assert dry_run["selected"] == 1
    assert dry_run["verified"] == 1
    assert dry_run["updated"] == 0
    assert first.object_key is None
    assert fake_s3.put_count == 0

    first_apply = migrate_batch(session=db_session, batch_size=1, apply=True, store=store)
    assert first_apply["updated"] == 1
    assert first.object_key == store.key_for(first.checksum)
    assert first.storage_backend == "s3"
    assert first.raw_body == first_body

    second_apply = migrate_batch(session=db_session, after_id=first.id, batch_size=1, apply=True, store=store)
    assert second_apply["updated"] == 1
    assert second.object_key == store.key_for(second.checksum)

    replay = migrate_batch(session=db_session, batch_size=2, apply=True, store=store)
    assert replay["selected"] == 0
    assert fake_s3.put_count == 2
