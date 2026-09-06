"""S3 static site for the deploy spike — W4.2 step 5.

Hosts infra/spike_test/index.html, a minimal page (not the real web/ frontend —
that's wired for real in W4.4) that calls the CloudFront endpoint and renders
the raw response. Purpose is only to prove "reachable from a browser through
the deployed path," per PLAN.md's spike checkpoint.

Idempotent: reruns reuse the existing bucket and just re-upload the page.

Usage:
    python infra/deploy_s3_site.py https://d2b6ljkmwrnf2n.cloudfront.net/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_SOURCE = REPO_ROOT / "infra" / "spike_test" / "index.html"
REGION = "us-east-1"


def bucket_name(sts) -> str:
    account = sts.get_caller_identity()["Account"]
    return f"pathwise-deploy-spike-{account}"


def ensure_bucket(s3, name: str) -> None:
    try:
        s3.head_bucket(Bucket=name)
        print(f"Reusing existing bucket {name}")
        return
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise

    # us-east-1 is the one region where CreateBucket must NOT include a
    # LocationConstraint — passing one there raises InvalidLocationConstraint.
    s3.create_bucket(Bucket=name)
    print(f"Created bucket {name}")


def configure_public_website(s3, name: str) -> None:
    s3.put_public_access_block(
        Bucket=name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": False,
            "IgnorePublicAcls": False,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    )
    s3.put_bucket_website(
        Bucket=name,
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}},
    )
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{name}/*",
        }],
    }
    s3.put_bucket_policy(Bucket=name, Policy=json.dumps(policy))
    print("Public access block disabled, static hosting + public-read policy set")


def upload_page(s3, name: str, endpoint: str) -> None:
    html = PAGE_SOURCE.read_text().replace("__ENDPOINT__", endpoint)
    s3.put_object(
        Bucket=name,
        Key="index.html",
        Body=html.encode("utf-8"),
        ContentType="text/html",
    )
    print("Uploaded index.html")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python infra/deploy_s3_site.py <cloudfront-url>")
    endpoint = sys.argv[1]

    sts = boto3.client("sts", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    name = bucket_name(sts)
    ensure_bucket(s3, name)
    configure_public_website(s3, name)
    upload_page(s3, name, endpoint)

    site_url = f"http://{name}.s3-website-{REGION}.amazonaws.com"
    print(f"\nSite URL: {site_url}")


if __name__ == "__main__":
    main()
