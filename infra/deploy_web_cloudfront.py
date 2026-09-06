"""CloudFront in front of the web/ S3 static site — fixes the Step 3 crash.

web/app.js hashes the request body with crypto.subtle.digest() before every
backend call (see callBackend() in web/app.js). SubtleCrypto only exists in a
secure context (HTTPS or localhost) - deploy_web.py serves the site from an
S3 static-website endpoint, and those never support TLS at all, so
crypto.subtle is undefined there and clicking "Build my plan" throws
"Cannot read properties of undefined (reading 'digest')" before the fetch
ever happens. This puts a CloudFront distribution in front of that same S3
website endpoint purely to get an HTTPS URL for the site.

No Origin Access Control here, unlike deploy_cloudfront.py's Lambda
distribution: the web bucket is already public-read (anyone can view the
site), so there is nothing to sign or restrict - CloudFront just terminates
TLS in front of the existing public origin.

Idempotent: reruns find the existing distribution by its Comment and reuse it.

Usage:
    python infra/deploy_web_cloudfront.py <s3-website-endpoint-domain>
"""

from __future__ import annotations

import sys

import boto3

DIST_COMMENT = "pathwise-web"
REGION = "us-east-1"  # CloudFront is global but its control API lives here


def find_existing_distribution(cf) -> dict | None:
    paginator = cf.get_paginator("list_distributions")
    for page in paginator.paginate():
        items = page.get("DistributionList", {}).get("Items", [])
        for item in items:
            if item.get("Comment") == DIST_COMMENT:
                return item
    return None


def ensure_distribution(cf, origin_domain: str) -> dict:
    existing = find_existing_distribution(cf)
    if existing:
        print(f"Reusing existing distribution {existing['Id']} ({existing['DomainName']})")
        return existing

    origin_id = "pathwise-web-s3-website"
    config = {
        "CallerReference": DIST_COMMENT,
        "Comment": DIST_COMMENT,
        "Enabled": True,
        "DefaultRootObject": "index.html",
        "Origins": {
            "Quantity": 1,
            "Items": [{
                "Id": origin_id,
                "DomainName": origin_domain,
                "CustomOriginConfig": {
                    # S3 website endpoints never serve HTTPS - http-only is the
                    # one origin protocol policy that can reach them at all.
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only",
                    "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                },
            }],
        },
        "DefaultCacheBehavior": {
            "TargetOriginId": origin_id,
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {
                "Quantity": 2,
                "Items": ["GET", "HEAD"],
                "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
            },
            # Managed-CachingDisabled: every redeploy's re-upload is visible
            # immediately with no separate invalidation step, matching the
            # one-command redeploy goal in PLAN.md W4.6. This site is small
            # enough that real caching buys nothing worth the staleness risk
            # during active development.
            "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        },
    }
    resp = cf.create_distribution(DistributionConfig=config)
    dist = resp["Distribution"]
    print(f"Created distribution {dist['Id']} ({dist['DomainName']}) — status: {dist['Status']}")
    return {"Id": dist["Id"], "DomainName": dist["DomainName"]}


def deploy_web_cloudfront(origin_domain: str) -> str:
    """Ensure the CloudFront distribution in front of the web/ S3 site. Returns its domain."""
    cf = boto3.client("cloudfront", region_name=REGION)
    dist = ensure_distribution(cf, origin_domain)
    return dist["DomainName"]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python infra/deploy_web_cloudfront.py <s3-website-endpoint-domain>")
    domain = deploy_web_cloudfront(sys.argv[1])
    print(f"\nSite CloudFront domain: https://{domain}")
    print("Propagation typically takes 5-15 minutes after its first creation.")


if __name__ == "__main__":
    main()
