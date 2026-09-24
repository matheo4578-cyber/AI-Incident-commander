#!/usr/bin/env python3
"""Permanently empty every version and delete marker from a versioned S3 bucket."""

from __future__ import annotations

import sys
from typing import Any

import boto3


def empty_versioned_bucket(bucket: str, *, s3: Any | None = None) -> int:
    client = s3 or boto3.client("s3")
    deleted = 0
    paginator = client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket):
        objects = [
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for group in (page.get("Versions", []), page.get("DeleteMarkers", []))
            for item in group
        ]
        for start in range(0, len(objects), 1000):
            batch = objects[start : start + 1000]
            if batch:
                response = client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": batch, "Quiet": True},
                )
                errors = (response or {}).get("Errors", [])
                if errors:
                    details = ", ".join(
                        f"{item.get('Key', '?')}:{item.get('Code', 'Unknown')}" for item in errors
                    )
                    raise RuntimeError(f"S3 version deletion failed: {details}")
                deleted += len(batch)
    return deleted


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: empty_versioned_bucket.py BUCKET")
    deleted = empty_versioned_bucket(sys.argv[1])
    print(f"Deleted {deleted} S3 object versions/delete markers from {sys.argv[1]}")


if __name__ == "__main__":
    main()
