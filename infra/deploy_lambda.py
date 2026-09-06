"""Create the proxy Lambda + Function URL in front of AgentCore Runtime — W4.2.

One-shot creation script for the deploy spike. Re-running it updates the
existing function's code and config in place rather than erroring, so it is
safe to run again after editing lambda_handler.py.

Lambda's built-in boto3/botocore layer does not know the bedrock-agentcore
service yet (it's new), so this bundles a fresh boto3+botocore into the
deployment zip instead of relying on the runtime default.

Usage:
    python infra/deploy_lambda.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import ClientError

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "infra" / ".build"
ZIP_PATH = REPO_ROOT / "infra" / ".build.zip"

FUNCTION_NAME = "pathwise-agent-proxy"
ROLE_NAME = "pathwise-agent-proxy-role"

# The full onboard/run call chains planner -> module/event/project agents -> scoring,
# several sequential Bedrock calls deep. That routinely runs past 30s, so both this and
# CloudFront's OriginReadTimeout (see deploy_cloudfront.py) need to agree on a longer
# budget - see lambda_handler.py's botocore Config for why 60 isn't itself enough headroom.
FUNCTION_TIMEOUT_SECONDS = 60


def load_agent_arn() -> tuple[str, str]:
    config = yaml.safe_load((REPO_ROOT / ".bedrock_agentcore.yaml").read_text())
    agent = config["agents"][config["default_agent"]]
    arn = agent["bedrock_agentcore"]["agent_arn"]
    region = agent["aws"]["region"]
    if not arn:
        sys.exit("No agent_arn in .bedrock_agentcore.yaml — run `agentcore deploy` first.")
    return arn, region


def build_zip() -> None:
    print("Building deployment package (bundling boto3/botocore)...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install",
            "--target", str(BUILD_DIR),
            "--only-binary=:all:", "--platform", "manylinux2014_x86_64",
            "--python-version", "3.11", "--implementation", "cp",
            "boto3",
        ],
        check=True,
    )
    shutil.copy(REPO_ROOT / "infra" / "lambda_handler.py", BUILD_DIR / "lambda_handler.py")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in BUILD_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(BUILD_DIR))
    print(f"  {ZIP_PATH} ({ZIP_PATH.stat().st_size // 1024} KB)")


def ensure_role(iam, agent_arn: str) -> str:
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }
    invoke_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "bedrock-agentcore:InvokeAgentRuntime",
            # AWS checks permission on both the bare runtime ARN and its
            # runtime-endpoint sub-resource (.../runtime-endpoint/DEFAULT)
            # depending on call path — grant both.
            "Resource": [agent_arn, f"{agent_arn}/runtime-endpoint/*"],
        }],
    }
    try:
        resp = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for the pathwise agent-proxy Lambda (W4.2 spike)",
        )
        role_arn = resp["Role"]["Arn"]
        print(f"Created role {ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        print(f"Reusing existing role {ROLE_NAME}")

    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="InvokeAgentRuntime",
        PolicyDocument=json.dumps(invoke_policy),
    )
    return role_arn


def ensure_function(lam, role_arn: str, agent_arn: str) -> str:
    with open(ZIP_PATH, "rb") as fh:
        zip_bytes = fh.read()

    # AWS_REGION is a reserved Lambda env var — the runtime sets it for us already.
    env = {"Variables": {"AGENT_RUNTIME_ARN": agent_arn}}
    try:
        resp = lam.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.11",
            Role=role_arn,
            Handler="lambda_handler.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=FUNCTION_TIMEOUT_SECONDS,
            MemorySize=256,
            Environment=env,
            Description="Proxy in front of AgentCore Runtime — W4.2 deploy spike",
        )
        print(f"Created function {FUNCTION_NAME}")
        function_arn = resp["FunctionArn"]
    except lam.exceptions.ResourceConflictException:
        print(f"Function {FUNCTION_NAME} exists, updating code and config")
        lam.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
        waiter = lam.get_waiter("function_updated")
        waiter.wait(FunctionName=FUNCTION_NAME)
        resp = lam.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Timeout=FUNCTION_TIMEOUT_SECONDS,
            MemorySize=256,
            Environment=env,
        )
        function_arn = resp["FunctionArn"]

    waiter = lam.get_waiter("function_active_v2")
    waiter.wait(FunctionName=FUNCTION_NAME)
    return function_arn


def ensure_function_url(lam) -> str:
    try:
        resp = lam.create_function_url_config(
            FunctionName=FUNCTION_NAME,
            AuthType="NONE",
        )
        print("Created Function URL")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise
        resp = lam.get_function_url_config(FunctionName=FUNCTION_NAME)
        print("Function URL already exists")

    try:
        lam.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="AllowPublicFunctionUrl",
            Action="lambda:InvokeFunctionUrl",
            Principal="*",
            FunctionUrlAuthType="NONE",
        )
    except lam.exceptions.ResourceConflictException:
        pass  # permission already granted from a previous run

    return resp["FunctionUrl"]


def deploy_lambda() -> str:
    """Build and deploy the proxy Lambda + Function URL. Returns the Function URL."""
    agent_arn, region = load_agent_arn()
    print(f"Agent ARN: {agent_arn}\nRegion: {region}\n")

    build_zip()

    iam = boto3.client("iam", region_name=region)
    lam = boto3.client("lambda", region_name=region)

    role_arn = ensure_role(iam, agent_arn)
    print("Waiting 10s for IAM role propagation...")
    time.sleep(10)

    ensure_function(lam, role_arn, agent_arn)
    return ensure_function_url(lam)


def main() -> None:
    url = deploy_lambda()
    print(f"\nFunction URL: {url}")
    print("Test it with:")
    print(f'  curl -X POST {url} -H "content-type: application/json" -d \'{{"prompt": "test"}}\'')


if __name__ == "__main__":
    main()
