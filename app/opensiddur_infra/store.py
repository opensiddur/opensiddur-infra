"""Atomic document access; production transactions and an equivalent test backend."""

import copy
import hashlib
import threading
from collections.abc import Callable


def document_id(key):
    return hashlib.sha256(key.encode()).hexdigest()


class MemoryStore:
    def __init__(self):
        self.data = {}
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            return copy.deepcopy(self.data.get(key))

    def atomic(self, keys, mutate: Callable):
        with self.lock:
            values = {key: copy.deepcopy(self.data.get(key)) for key in keys}
            result = mutate(values)
            for key, value in values.items():
                if value is None:
                    self.data.pop(key, None)
                else:
                    self.data[key] = value
            return copy.deepcopy(result)

    def list(self, kind, owner=None, filters=None):
        with self.lock:
            result = [
                copy.deepcopy(v)
                for v in self.data.values()
                if v.get("kind") == kind and (owner is None or v.get("owner") == owner)
            ]
            for field, (operator, value) in (filters or {}).items():
                if operator == "in":
                    result = [r for r in result if r.get(field) in value]
                elif operator == "<=":
                    result = [r for r in result if r.get(field, float("inf")) <= value]
                else:
                    raise ValueError("Unsupported query")
            return result


class FirestoreStore:
    def __init__(self, project, credentials=None):
        from google.cloud import firestore

        self.db = firestore.Client(project=project, credentials=credentials)
        self.collection = self.db.collection("builder_records")

    def ref(self, key):
        return self.collection.document(document_id(key))

    def get(self, key):
        doc = self.ref(key).get()
        return doc.to_dict() if doc.exists else None

    def atomic(self, keys, mutate):
        from google.cloud import firestore

        @firestore.transactional
        def apply(transaction):
            values = {}
            for key in keys:
                doc = self.ref(key).get(transaction=transaction)
                values[key] = doc.to_dict() if doc.exists else None
            result = mutate(values)
            for key, value in values.items():
                if value is None:
                    transaction.delete(self.ref(key))
                else:
                    from datetime import datetime, timezone

                    if "expires" in value and (
                        value.get("kind") != "build"
                        or value.get("state")
                        in {"succeeded", "partial", "failed", "cancelled", "expired"}
                    ):
                        value["expires_at"] = datetime.fromtimestamp(
                            value["expires"], timezone.utc
                        )
                    transaction.set(self.ref(key), value)
            return result

        return apply(self.db.transaction())

    def list(self, kind, owner=None, filters=None):
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.collection.where(filter=FieldFilter("kind", "==", kind))
        if owner is not None:
            query = query.where(filter=FieldFilter("owner", "==", owner))
        for field, (operator, value) in (filters or {}).items():
            query = query.where(filter=FieldFilter(field, operator, value))
        return [doc.to_dict() for doc in query.stream()]
