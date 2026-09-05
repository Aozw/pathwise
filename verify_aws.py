"""Preflight check for the sandbox AWS account.

Run this FIRST, before any other AWS work, and again whenever something starts
failing with an auth error. It answers, in order:

  1. Are the three credentials present in .env?
  2. Do they actually authenticate, and to which account?
  3. Which Claude models does this sandbox let us call, in this region?
  4. Does a real Bedrock call succeed, and what does it report for tokens?

Usage:
    python scripts/verify_aws.py

Costs about one thousandth of a cent. Nothing here creates a resource.
"""

from __future__ import annotations

import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")
REQUIRED = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")


def fail(message: str, hint: str = "") -> None:
    print(f"\n  FAILED: {message}")
    if hint:
        print(f"  {hint}")
    sys.exit(1)


def check_env() -> None:
    print("1. Credentials in environment")
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        fail(
            f"missing {', '.join(missing)}",
            "Copy all three from the AWS access portal: Accounts tab, expand the\n"
            "  sandbox account, Access keys, 'Option 1: Set AWS environment variables'.\n"
            "  AWS_SESSION_TOKEN is required. These are temporary credentials.",
        )
    print(f"   ok, all three present, region {REGION}")


def check_identity() -> None:
    print("\n2. Credentials authenticate")
    try:
        identity = boto3.client("sts", region_name=REGION).get_caller_identity()
    except (ClientError, BotoCoreError) as exc:
        fail(
            str(exc),
            "If this says the token is expired or invalid, that is the 12 hour\n"
            "  expiry. Log back into the access portal and copy the three values again.",
        )
    print(f"   ok, account {identity['Account']}")
    print(f"   role {identity['Arn'].split('/')[-2] if '/' in identity['Arn'] else identity['Arn']}")


def list_models() -> list[str]:
    print("\n3. Claude models callable in this region")
    bedrock = boto3.client("bedrock", region_name=REGION)

    # Bare foundation-model ids and inference-profile ids are not interchangeable: a
    # newer model's bare id often has inferenceTypesSupported == ["INFERENCE_PROFILE"],
    # meaning converse() rejects it and only the region-prefixed profile id works. Keep
    # the two apart so the id actually picked below is one that can be called.
    bare_ids: list[str] = []
    legacy_bare_ids: set[str] = set()
    try:
        for model in bedrock.list_foundation_models()["modelSummaries"]:
            if "claude" not in model["modelId"].lower():
                continue
            # Skip legacy models entirely rather than surface an id that Bedrock will
            # reject with "marked by provider as Legacy... access denied". Remembered
            # separately so inference profiles routing to a legacy model (below) can
            # be filtered too - a profile's own `status` is always "ACTIVE" regardless
            # of the underlying model's lifecycle.
            if model.get("modelLifecycle", {}).get("status") == "LEGACY":
                legacy_bare_ids.add(model["modelId"])
                continue
            bare_ids.append(model["modelId"])
    except (ClientError, BotoCoreError) as exc:
        fail(
            str(exc),
            f"Access denied here almost always means wrong region. You are in\n"
            f"  {REGION}; the organisers' guide says Bedrock is granted in us-east-1.",
        )

    profile_ids: list[str] = []
    try:
        for profile in bedrock.list_inference_profiles()["inferenceProfileSummaries"]:
            if "claude" not in profile["inferenceProfileId"].lower():
                continue
            underlying = profile.get("models", [{}])[0].get("modelArn", "").rsplit("/", 1)[-1]
            if underlying in legacy_bare_ids:
                continue
            profile_ids.append(profile["inferenceProfileId"])
    except (ClientError, BotoCoreError):
        print("   (inference profiles not listable, using bare model ids)")

    all_ids = sorted(set(bare_ids) | set(profile_ids))
    if not all_ids:
        fail(
            "no Claude models available",
            "Open the Bedrock console in this region, go to Model access, and\n"
            "  check what is enabled. You may need to request access.",
        )

    for model_id in all_ids:
        marker = "  <-- cheapest, use this" if "haiku" in model_id.lower() else ""
        print(f"   {model_id}{marker}")

    # Profile ids are always directly invocable; a bare id sometimes is not. Among
    # profile ids, prefer ones prefixed for this region's geography (e.g. "us." for
    # us-east-1) over "global." ones: the sandbox account's service control policy
    # denies bedrock:InvokeModel on "global." profiles even though list_inference_profiles
    # happily lists them, so picking one blind fails with AccessDeniedException.
    geo = REGION.split("-")[0]  # "us-east-1" -> "us"
    regional = [p for p in profile_ids if p.startswith(f"{geo}.")]
    return sorted(set(regional) or set(profile_ids)) or sorted(set(bare_ids))


def test_call(model_id: str) -> None:
    print(f"\n4. Live call to {model_id}")
    runtime = boto3.client("bedrock-runtime", region_name=REGION)
    try:
        response = runtime.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with the word: ready"}]}],
            inferenceConfig={"temperature": 0, "maxTokens": 20},
        )
    except (ClientError, BotoCoreError) as exc:
        fail(
            str(exc),
            "If this is ValidationException about an inference profile, the model\n"
            "  needs its region-prefixed profile id instead of the bare id.",
        )

    text = response["output"]["message"]["content"][0]["text"].strip()
    usage = response.get("usage", {})
    print(f"   ok, model replied: {text!r}")
    print(f"   tokens in {usage.get('inputTokens')}, out {usage.get('outputTokens')}")
    print(f"\n   Put this in your .env:\n   MODEL_HAIKU={model_id}")


def main() -> None:
    print(f"Preflight check, region {REGION}\n" + "-" * 50)
    check_env()
    check_identity()
    models = list_models()

    haiku = [m for m in models if "haiku" in m.lower()]
    if not haiku:
        print("\n   No Haiku model found. Everything below will cost more per call.")
    test_call(haiku[0] if haiku else models[0])

    print("\n" + "-" * 50)
    print("All checks passed. Safe to start building.")


if __name__ == "__main__":
    main()
