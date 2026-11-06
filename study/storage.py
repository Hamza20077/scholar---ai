from whitenoise.storage import CompressedManifestStaticFilesStorage


class ManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Serve unhashed source URLs in tests before collectstatic creates a manifest."""

    manifest_strict = False
