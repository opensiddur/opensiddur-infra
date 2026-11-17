import datetime
import time


class Storage:
    def __init__(self, config, credentials=None):
        from google.cloud import storage

        self.config = config
        self.bucket = storage.Client(
            project=config.project, credentials=credentials
        ).bucket(config.bucket)

    def put(self, name, data, content_type="application/octet-stream", expires=None):
        blob = self.bucket.blob(name)
        blob.cache_control = "private, no-store"
        if expires:
            blob.metadata = {"expires": str(expires)}
        blob.upload_from_string(data, content_type=content_type, timeout=60, retry=None)
        return {
            "name": name.rsplit("/", 1)[-1],
            "object": name,
            "size": len(data),
            "content_type": content_type,
        }

    def read(self, name):
        return self.bucket.blob(name).download_as_bytes()

    def delete_prefix(self, prefix):
        for blob in self.bucket.list_blobs(prefix=prefix):
            blob.delete()

    def url(self, name, expires, content_type):
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        seconds = int(min(300, expires - time.time()))
        if seconds <= 0:
            from .builds import Rejected

            raise Rejected("Build expired", 410)
        return self.bucket.blob(name).generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=seconds),
            service_account_email=self.config.worker_email,
            access_token=credentials.token,
            response_disposition='attachment; filename="'
            + name.rsplit("/", 1)[-1]
            + '"',
            response_type=content_type,
        )

    def list_files(self, prefix):
        return [
            {"object": b.name, "size": b.size, "generation": b.generation}
            for b in self.bucket.list_blobs(prefix=prefix)
        ]

    def copy_to(self, item, destination):
        from google.api_core.exceptions import NotFound, PreconditionFailed

        blob = self.bucket.blob(item["object"], generation=item["generation"])
        try:
            with blob.open(
                "rb", chunk_size=1024 * 1024, timeout=60, retry=None
            ) as source:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
        except (NotFound, PreconditionFailed) as exc:
            raise FileNotFoundError(item["object"]) from exc

    def export_file(self, name, expires):
        blob = self.bucket.blob(name)
        blob.cache_control = "private, no-store"
        blob.metadata = {"expires": str(expires)}
        blob.content_type = "application/zip"
        # ZipFile supports unseekable output. GCS buffers only bounded upload chunks.
        return blob.open(
            "wb", chunk_size=8 * 1024 * 1024, ignore_flush=True, timeout=60, retry=None
        )
