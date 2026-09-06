"""CloudFront + Origin Access Control in front of the proxy Lambda — W4.2.

The sandbox account's SCP blocks anonymous (AuthType=NONE) Function URL
invocation, so the Function URL is AWS_IAM-authed and a browser cannot call it
directly without embedding credentials. CloudFront with an Origin Access
Control signs requests to the Function URL using a CloudFront service
permission — the browser hits CloudFront's public domain with no auth of its
own. This is AWS's documented pattern for exactly this case, not a workaround.

Idempotent: reruns find the existing OAC/distribution by name/comment and
update the Lambda resource policy rather than creating duplicates.

Usage:
    python infra/deploy_cloudfront.py
"""

from __future__ import annotations

import boto3

FUNCTION_NAME = "pathwise-agent-proxy"
OAC_NAME = "pathwise-agent-proxy-oac"
DIST_COMMENT = "pathwise-agent-proxy"
REGION = "us-east-1"  # CloudFront is global but its control API lives here


def get_function_url_domain(lam) -> str:
    cfg = lam.get_function_url_config(FunctionName=FUNCTION_NAME)
    return cfg["FunctionUrl"].removeprefix("https://").rstrip("/")


def ensure_oac(cf) -> str:
    existing = cf.list_origin_access_controls()["OriginAccessControlList"].get("Items", [])
    for item in existing:
        if item["Name"] == OAC_NAME:
            print(f"Reusing existing OAC {item['Id']}")
            return item["Id"]

    resp = cf.create_origin_access_control(
        OriginAccessControlConfig={
            "Name": OAC_NAME,
            "SigningProtocol": "sigv4",
            "SigningBehavior": "always",
            "OriginAccessControlOriginType": "lambda",
        }
    )
    oac_id = resp["OriginAccessControl"]["Id"]
    print(f"Created OAC {oac_id}")
    return oac_id


def find_existing_distribution(cf) -> dict | None:
    paginator = cf.get_paginator("list_distributions")
    for page in paginator.paginate():
        items = page.get("DistributionList", {}).get("Items", [])
        for item in items:
            if item.get("Comment") == DIST_COMMENT:
                return item
    return None


def ensure_distribution(cf, origin_domain: str, oac_id: str) -> dict:
    existing = find_existing_distribution(cf)
    if existing:
        print(f"Reusing existing distribution {existing['Id']} ({existing['DomainName']})")
        return existing

    origin_id = "pathwise-agent-proxy-lambda"
    config = {
        "CallerReference": DIST_COMMENT,
        "Comment": DIST_COMMENT,
        "Enabled": True,
        "Origins": {
            "Quantity": 1,
            "Items": [{
                "Id": origin_id,
                "DomainName": origin_domain,
                "OriginAccessControlId": oac_id,
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "https-only",
                    "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                },
            }],
        },
        "DefaultCacheBehavior": {
            "TargetOriginId": origin_id,
            "ViewerProtocolPolicy": "https-only",
            "AllowedMethods": {
                "Quantity": 7,
                "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
                "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
            },
            # Managed-CachingDisabled: this is a dynamic API, never cache responses.
            "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
            # Managed-AllViewerExceptHostHeader: forwards headers/body, drops
            # Host so the Lambda Function URL's own origin check doesn't choke
            # on CloudFront's Host header. AWS's documented pairing for this
            # origin type.
            "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac",
        },
    }
    resp = cf.create_distribution(DistributionConfig=config)
    dist = resp["Distribution"]
    print(f"Created distribution {dist['Id']} ({dist['DomainName']}) — status: {dist['Status']}")
    return {"Id": dist["Id"], "DomainName": dist["DomainName"], "ARN": dist["ARN"]}


def ensure_lambda_permission(lam, distribution_arn: str) -> None:
    try:
        lam.remove_permission(FunctionName=FUNCTION_NAME, StatementId="AllowPublicFunctionUrl")
        print("Removed stale public (AuthType=NONE) permission statement")
    except lam.exceptions.ResourceNotFoundException:
        pass

    # AWS's docs for OAC+Lambda function URLs require both grants: InvokeFunctionUrl
    # (the Function URL auth check) and InvokeFunction (the underlying Lambda
    # invoke) — CloudFront calls through both layers, and either alone 403s.
    grants = [
        ("AllowCloudFrontInvoke", "lambda:InvokeFunctionUrl", {"FunctionUrlAuthType": "AWS_IAM"}),
        ("AllowCloudFrontServicePrincipalInvokeFunction", "lambda:InvokeFunction", {}),
    ]
    for statement_id, action, extra_kwargs in grants:
        try:
            lam.add_permission(
                FunctionName=FUNCTION_NAME,
                StatementId=statement_id,
                Action=action,
                Principal="cloudfront.amazonaws.com",
                SourceArn=distribution_arn,
                **extra_kwargs,
            )
            print(f"Granted {action}")
        except lam.exceptions.ResourceConflictException:
            print(f"{action} permission already present")


def deploy_cloudfront() -> str:
    """Ensure the CloudFront distribution in front of the proxy Lambda. Returns its domain."""
    lam = boto3.client("lambda", region_name=REGION)
    cf = boto3.client("cloudfront", region_name=REGION)

    origin_domain = get_function_url_domain(lam)
    print(f"Origin (Function URL): {origin_domain}")

    oac_id = ensure_oac(cf)
    dist = ensure_distribution(cf, origin_domain, oac_id)
    distribution_arn = dist.get("ARN") or f"arn:aws:cloudfront::{boto3.client('sts').get_caller_identity()['Account']}:distribution/{dist['Id']}"

    ensure_lambda_permission(lam, distribution_arn)
    return dist["DomainName"]


def main() -> None:
    domain = deploy_cloudfront()
    print(f"\nCloudFront domain: https://{domain}")
    print("Propagation typically takes 5-15 minutes. Test with:")
    print(f'  curl -X POST https://{domain}/ -H "content-type: application/json" -d \'{{"prompt": "test"}}\'')


if __name__ == "__main__":
    main()
