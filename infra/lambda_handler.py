"""Lambda proxy in front of the AgentCore Runtime — W4.2 deploy spike.

The browser can't call bedrock-agentcore:InvokeAgentRuntime directly (that needs
SigV4-signed AWS credentials); this Lambda holds the IAM permission to do so and
exposes a plain HTTPS endpoint via its Function URL instead.

Every response, including error responses, carries CORS headers. A Lambda that
throws without them makes the browser report "CORS error", which sends whoever
is debugging looking in the wrong place (S3 page, Function URL config) instead
of at the actual failure below.

Required Lambda environment variable:
    AGENT_RUNTIME_ARN  — the arn:aws:bedrock-agentcore:...:runtime/... printed
                          by `agentcore deploy`.

The Lambda's own boto3/botocore (bundled in the deployment package, not the
runtime's built-in layer) must be new enough to know the bedrock-agentcore
service model. Bundle a requirements.txt-based layer or package if invocations
fail with "Unknown service: 'bedrock-agentcore'".
"""

from __future__ import annotations

import json
import os
import uuid

import boto3
from botocore.config import Config

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    # x-amz-content-sha256 is required alongside content-type: CloudFront's OAC
    # signs the request to the Lambda Function URL, but Lambda needs the client's
    # own body hash for unsigned POST/PUT (see infra/spike_test/index.html). Without
    # it here, the browser's preflight rejects the header and every real call from
    # web/ fails as a CORS error before ever reaching this handler - W4.4.
    "Access-Control-Allow-Headers": "content-type, x-amz-content-sha256",
    "Content-Type": "application/json",
}

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")

_client = boto3.client(
    "bedrock-agentcore",
    region_name=REGION,
    config=Config(connect_timeout=5, read_timeout=25, retries={"max_attempts": 2}),
)


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


def handler(event: dict, _context) -> dict:
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}

    raw_body = event.get("body") or "{}"
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return _response(400, {"error": "body must be valid JSON"})

    try:
        result = _client.invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            # AgentCore requires >= 33 chars; a bare uuid4 (36 chars) clears that.
            runtimeSessionId=str(uuid.uuid4()),
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(payload).encode("utf-8"),
        )
        agent_response = json.loads(result["response"].read())
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see module docstring
        return _response(502, {"error": "agent invocation failed", "detail": str(exc)})

    return _response(200, agent_response)
