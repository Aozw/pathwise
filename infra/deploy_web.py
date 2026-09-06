"""S3 static site for the real frontend — W4.6.

Uploads `web/` (the stripped-down Preview_V3 frontend, not
`infra/spike_test/`) to its own S3 bucket, templating `web/app.js`'s
`__ENDPOINT__` placeholder with the CloudFront domain in front of the proxy
Lambda. Same public-static-website pattern as `deploy_s3_site.py`, kept as a
separate bucket so the spike page and the real frontend don't overwrite each
other.

The bucket's own S3 website endpoint is HTTP-only (S3 website endpoints never
support TLS), which broke `web/app.js`'s `crypto.subtle.digest()` call -
SubtleCrypto doesn't exist outside a secure context, so Step 3 of onboarding
threw "Cannot read properties of undefined (reading 'digest')" the moment a
student clicked "Build my plan". `deploy_web_cloudfront.py` puts a second,
unrelated CloudFront distribution in front of this bucket purely to get an
HTTPS URL; see that module for why it needs no OAC.

Idempotent: reruns reuse the existing bucket and just re-upload the files.

Usage:
    python infra/deploy_web.py <cloudfront-domain-or-url>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from deploy_web_cloudfront import deploy_web_cloudfront

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
REGION = "us-east-1"

_CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
}


def bucket_name(sts) -> str:
    account = sts.get_caller_identity()["Account"]
    return f"pathwise-web-{account}"


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


def upload_site(s3, name: str, endpoint: str) -> None:
    for path in sorted(WEB_DIR.iterdir()):
        if not path.is_file():
            continue
        content_type = _CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        body = path.read_text(encoding="utf-8")
        if path.name == "app.js":
            body = body.replace("__ENDPOINT__", endpoint)
        s3.put_object(Bucket=name, Key=path.name, Body=body.encode("utf-8"), ContentType=content_type)
        print(f"  uploaded {path.name} ({content_type})")


def deploy_web(cloudfront_domain_or_url: str) -> str:
    """Upload `web/` to S3, wiring app.js at the CloudFront endpoint, then front
    the site itself with its own CloudFront distribution so it's served over
    HTTPS. Returns the site's HTTPS URL.
    """
    endpoint = cloudfront_domain_or_url
    if not endpoint.startswith("http"):
        endpoint = f"https://{endpoint}/"

    sts = boto3.client("sts", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    name = bucket_name(sts)
    ensure_bucket(s3, name)
    configure_public_website(s3, name)
    upload_site(s3, name, endpoint)

    website_domain = f"{name}.s3-website-{REGION}.amazonaws.com"
    site_domain = deploy_web_cloudfront(website_domain)
    return f"https://{site_domain}"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python infra/deploy_web.py <cloudfront-domain-or-url>")
    site_url = deploy_web(sys.argv[1])
    print(f"\nSite URL: {site_url}")


if __name__ == "__main__":
    main()
