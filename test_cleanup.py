import pytest

from scripts.empty_versioned_bucket import empty_versioned_bucket


class FakePaginator:
    def paginate(self, *, Bucket: str):
        assert Bucket == "reports"
        yield {
            "Versions": [
                {"Key": "reports/inc-1.json", "VersionId": "v1"},
                {"Key": "reports/inc-1.json", "VersionId": "v2"},
            ],
            "DeleteMarkers": [{"Key": "reports/inc-2.json", "VersionId": "marker-1"}],
        }


class FakeS3:
    def __init__(self, *, errors: bool = False) -> None:
        self.deleted: list[dict] = []
        self.errors = errors

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_object_versions"
        return FakePaginator()

    def delete_objects(self, **kwargs) -> None:
        self.deleted.extend(kwargs["Delete"]["Objects"])
        if self.errors:
            return {"Errors": [{"Key": "reports/inc-1.json", "Code": "AccessDenied"}]}
        return {"Errors": []}


def test_empty_versioned_bucket_deletes_versions_and_markers() -> None:
    s3 = FakeS3()

    count = empty_versioned_bucket("reports", s3=s3)

    assert count == 3
    assert {item["VersionId"] for item in s3.deleted} == {"v1", "v2", "marker-1"}


def test_empty_versioned_bucket_fails_on_partial_delete_error() -> None:
    with pytest.raises(RuntimeError, match="AccessDenied"):
        empty_versioned_bucket("reports", s3=FakeS3(errors=True))
