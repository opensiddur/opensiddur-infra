import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "retention", Path(__file__).resolve().parents[1] / "scripts/check_retention.py"
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_repository_retention_policy():
    policy.validate_source()


@pytest.mark.parametrize(
    "change",
    [
        {"versioning": {"enabled": True}},
        {"softDeletePolicy": {"retentionDurationSeconds": "2678400"}},
        {"retentionPolicy": {"retentionPeriod": "60"}},
        {"lifecycle": {"rule": [{"condition": {"age": 31}}]}},
    ],
)
def test_live_bucket_policy_rejects_drift(change):
    bucket = {"lifecycle": {"rule": [{"condition": {"age": 30}}]}}
    bucket.update(change)
    with pytest.raises(ValueError):
        policy.validate_bucket(bucket)


def test_plan_rejects_backups_even_with_short_retention_until_restore_is_safe():
    with pytest.raises(ValueError):
        policy.validate_plan(
            {
                "planned_values": {
                    "root_module": {
                        "resources": [
                            {
                                "type": "google_firestore_backup_schedule",
                                "values": {"retention": "86400s"},
                            }
                        ]
                    }
                }
            }
        )
