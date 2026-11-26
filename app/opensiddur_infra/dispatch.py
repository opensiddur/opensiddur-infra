import json
from datetime import timedelta


class Dispatcher:
    def __init__(self, config, store):
        self.config, self.store = config, store

    def enqueue(self, identifier):
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(
            self.config.project, self.config.region, self.config.queue
        )
        task = {
            "name": f"{parent}/tasks/build-{identifier}",
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": self.config.api_url + "/internal/dispatch",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"id": identifier}).encode(),
                "oidc_token": {
                    "service_account_email": self.config.dispatcher_email,
                    "audience": self.config.audience,
                },
            },
        }
        try:
            client.create_task(parent=parent, task=task)
        except AlreadyExists:
            pass

    def launch(self, build):
        if build["type"] == "full":
            from google.cloud import run_v2

            job = build.get("job") or self.config.job
            run_v2.JobsClient().run_job(
                request={
                    "name": job,
                    "overrides": {
                        "container_overrides": [
                            {"env": [{"name": "BUILD_ID", "value": build["id"]}]}
                        ],
                        "timeout": timedelta(seconds=build["seconds"]),
                    },
                }
            )
        else:
            from google.api_core.exceptions import AlreadyExists
            from google.cloud import tasks_v2

            client = tasks_v2.CloudTasksClient()
            parent = client.queue_path(
                self.config.project, self.config.region, "previews"
            )
            task = {
                "name": f"{parent}/tasks/preview-{build['id']}",
                "dispatch_deadline": timedelta(seconds=360),
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": (build.get("preview_url") or self.config.preview_url)
                    + "/process",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"id": build["id"]}).encode(),
                    "oidc_token": {
                        "service_account_email": self.config.dispatcher_email,
                        "audience": build.get("preview_url") or self.config.preview_url,
                    },
                },
            }
            try:
                client.create_task(parent=parent, task=task)
            except AlreadyExists:
                pass

    def launch_operation(self, identifier):
        from google.cloud import run_v2

        run_v2.JobsClient().run_job(
            request={
                "name": self.config.data_job,
                "overrides": {
                    "container_overrides": [
                        {"env": [{"name": "OPERATION_ID", "value": identifier}]}
                    ]
                },
            }
        )

    def stop(self, build):
        """Return true only when the execution cannot publish again."""
        import time

        if build["type"] != "full":
            return time.time() > build["started"] + 390
        from google.api_core.exceptions import NotFound
        from google.cloud import run_v2

        job = build.get("job") or self.config.job
        name = job + "/executions/" + build["execution"]
        client = run_v2.ExecutionsClient()
        try:
            execution = client.get_execution(name=name)
            if execution.completion_time:
                return True
            client.cancel_execution(name=name)
            return False
        except NotFound:
            return True
