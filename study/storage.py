import os
import posixpath
import uuid
from io import BytesIO

from django.core.exceptions import SuspiciousFileOperation
from django.core.files import File
from django.core.files.utils import validate_file_name
from django.core.files.storage import Storage
from whitenoise.storage import CompressedManifestStaticFilesStorage


def get_blob_client():
    """Import lazily so local filesystem storage works without the Vercel SDK."""
    from vercel.blob import sync as blob

    return blob


class ManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Serve unhashed source URLs in tests before collectstatic creates a manifest."""

    manifest_strict = False


class VercelPrivateBlobStorage(Storage):
    """Django storage for private Vercel Blob objects; no public file URLs."""

    def get_available_name(self, name, max_length=None):
        name = validate_file_name(name, allow_relative_path=True)
        directory, filename = posixpath.split(name)
        stem, extension = os.path.splitext(filename)
        filename = f"{stem}-{uuid.uuid4().hex}{extension}"
        available_name = posixpath.join(directory, filename) if directory else filename
        if max_length and len(available_name) > max_length:
            excess = len(available_name) - max_length
            stem = stem[:-excess] if excess < len(stem) else "file"
            filename = f"{stem}-{uuid.uuid4().hex}{extension}"
            available_name = posixpath.join(directory, filename) if directory else filename
            if len(available_name) > max_length:
                raise SuspiciousFileOperation("The generated private blob name exceeds max_length.")
        return available_name

    def _save(self, name, content):
        name = validate_file_name(name, allow_relative_path=True)
        content.seek(0)
        result = get_blob_client().put_blob(
            name,
            content.file,
            access="private",
            content_length=content.size,
            content_type="application/pdf",
        )
        return result.pathname

    def _open(self, name, mode="rb"):
        if mode not in {"r", "rb"}:
            raise ValueError("Private Vercel Blob files are read-only through this storage backend.")
        result = get_blob_client().get_blob(name, access="private")
        return File(BytesIO(result.body), name=name)

    def delete(self, name):
        if name:
            get_blob_client().delete_blob(name)

    def exists(self, name):
        blob = get_blob_client()
        try:
            blob.head_blob(name)
            return True
        except blob.BlobNotFoundError:
            return False

    def size(self, name):
        return get_blob_client().head_blob(name).size

    def url(self, name):
        raise ValueError("Private study files are never exposed through public URLs.")
