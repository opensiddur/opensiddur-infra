import datetime
import time


class Storage:
    def __init__(self, config):
        from google.cloud import storage

        self.config = config
        self.bucket = storage.Client(project=config.project).bucket(config.bucket)

    def put(self, name, data, content_type="application/octet-stream", expires=None):
        blob = self.bucket.blob(name)
        blob.cache_control = "private, no-store"
        if expires:
            blob.metadata = {"expires": str(expires)}
        blob.upload_from_string(data, content_type=content_type)
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
        return self.bucket.blob(name).generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(
                seconds=max(1, min(300, int(expires - time.time())))
            ),
            service_account_email=self.config.worker_email,
            access_token=credentials.token,
            response_disposition='attachment; filename="'
            + name.rsplit("/", 1)[-1]
            + '"',
            response_type=content_type,
        )
