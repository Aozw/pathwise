"""One-command redeploy — W4.6.

Chains every step needed to bring the deployed system up to date with
whatever is checked out locally:

    0. Load `.env` and confirm AWS credentials are present and not expired,
       so everyone hits the same one clear error instead of whatever each
       step's own tool happens to raise. See `_ensure_credentials()`.
    1. `agentcore launch` — rebuilds and pushes the AgentCore Runtime
       container for `src/entrypoint.py`, updating the existing agent
       recorded in `.bedrock_agentcore.yaml` rather than creating a new one.
    2. `deploy_lambda.deploy_lambda()` — rebuilds the proxy Lambda's zip
       (picks up changes to `infra/lambda_handler.py`) and updates the
       function + Function URL.
    3. `deploy_cloudfront.deploy_cloudfront()` — ensures the CloudFront
       distribution in front of the Lambda (idempotent; a no-op after the
       first run unless the Function URL itself changed).
    4. `deploy_web.deploy_web()` — uploads the real `web/` frontend to S3,
       wiring `app.js` at the CloudFront domain from step 3, then fronts the
       site itself with its own CloudFront distribution (see
       `deploy_web_cloudfront.py`) so it's reachable over HTTPS - required
       for `web/app.js`'s `crypto.subtle.digest()` call to work at all.

Each step is idempotent on its own (see their module docstrings), which is
what makes running all four unconditionally on every redeploy cheap enough
to actually do. Per PLAN.md W4.6 / CHECKLIST.md Step 14: if redeploying
takes more than one command, people stop doing it and the deployed version
drifts from `main`.

This script never used to load `.env` itself — `src/config.py` calls
`load_dotenv()`, but this script never imports it, so `.env`'s AWS_* values
never reached this process or the `agentcore launch` subprocess it shells
out to, even with a fully filled-in `.env`. That surfaced as `agentcore`'s
own "No AWS credentials found" or a bare boto3 traceback deep inside step 2,
depending on which step happened to touch AWS first. Step 0 fixes that and
turns the other common failure (the access portal's temporary credentials
expire every 12 hours) into one clear message instead of a stack trace.

Usage:
    python infra/deploy.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_cloudfront import deploy_cloudfront  # noqa: E402
from deploy_lambda import deploy_lambda  # noqa: E402
from deploy_web import deploy_web  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_ENV_VARS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION")


def missing_env_vars(environ: dict[str, str]) -> list[str]:
    """Pure so it's unit testable without touching the real environment."""
    return [name for name in REQUIRED_ENV_VARS if not environ.get(name)]


def _ensure_credentials() -> None:
    print("=== 0/4  credentials ===")
    load_dotenv()

    missing = missing_env_vars(os.environ)
    if missing:
        sys.exit(
            f"Missing from .env (or empty): {', '.join(missing)}. Copy fresh values "
            "from the AWS access portal — see .env.example for exactly where."
        )

    try:
        identity = boto3.client("sts", region_name=os.environ["AWS_REGION"]).get_caller_identity()
    except (ClientError, NoCredentialsError) as exc:
        sys.exit(
            f"AWS rejected the credentials in .env ({exc}). These are temporary STS "
            "credentials that expire every 12 hours — log back into the access portal "
            "and paste fresh values into .env, per .env.example."
        )
    print(f"  authenticated as {identity['Arn']}")


def relaunch_agent() -> None:
    print("\n=== 1/4  agentcore launch ===")
    try:
        subprocess.run(["agentcore", "launch"], cwd=REPO_ROOT, check=True)
    except FileNotFoundError:
        sys.exit(
            "`agentcore` CLI not found on PATH. Install the AgentCore starter "
            "toolkit (see PLAN.md section 6, step 3) and run `agentcore configure` "
            "once if this is a fresh machine."
        )


def main() -> None:
    _ensure_credentials()
    relaunch_agent()

    print("\n=== 2/4  Lambda proxy ===")
    function_url = deploy_lambda()

    print("\n=== 3/4  CloudFront ===")
    cloudfront_domain = deploy_cloudfront()

    print("\n=== 4/4  web/ frontend ===")
    site_url = deploy_web(cloudfront_domain)

    print("\nDeploy complete.")
    print(f"  Function URL:          {function_url}")
    print(f"  API CloudFront domain: https://{cloudfront_domain}")
    print(f"  Site URL:              {site_url}")
    print(
        "\nCloudFront propagation can take 5-15 minutes after its first creation; "
        "a plain code/content update is faster."
    )


if __name__ == "__main__":
    main()
