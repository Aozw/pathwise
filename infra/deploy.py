"""One-command redeploy — W4.6.

Chains every step needed to bring the deployed system up to date with
whatever is checked out locally:

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
       wiring `app.js` at the CloudFront domain from step 3.

Each step is idempotent on its own (see their module docstrings), which is
what makes running all four unconditionally on every redeploy cheap enough
to actually do. Per PLAN.md W4.6 / CHECKLIST.md Step 14: if redeploying
takes more than one command, people stop doing it and the deployed version
drifts from `main`.

Usage:
    python infra/deploy.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_cloudfront import deploy_cloudfront  # noqa: E402
from deploy_lambda import deploy_lambda  # noqa: E402
from deploy_web import deploy_web  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def relaunch_agent() -> None:
    print("=== 1/4  agentcore launch ===")
    try:
        subprocess.run(["agentcore", "launch"], cwd=REPO_ROOT, check=True)
    except FileNotFoundError:
        sys.exit(
            "`agentcore` CLI not found on PATH. Install the AgentCore starter "
            "toolkit (see PLAN.md section 6, step 3) and run `agentcore configure` "
            "once if this is a fresh machine."
        )


def main() -> None:
    relaunch_agent()

    print("\n=== 2/4  Lambda proxy ===")
    function_url = deploy_lambda()

    print("\n=== 3/4  CloudFront ===")
    cloudfront_domain = deploy_cloudfront()

    print("\n=== 4/4  web/ frontend ===")
    site_url = deploy_web(cloudfront_domain)

    print("\nDeploy complete.")
    print(f"  Function URL:      {function_url}")
    print(f"  CloudFront domain: https://{cloudfront_domain}")
    print(f"  Site URL:          {site_url}")
    print(
        "\nCloudFront propagation can take 5-15 minutes after its first creation; "
        "a plain code/content update is faster."
    )


if __name__ == "__main__":
    main()
