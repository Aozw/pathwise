"""Preflight check for the Devpost hackathon search endpoint.

W2.0 / CHECKLIST.md Step 4: do this before building anything that depends on Devpost as a
live source, because the endpoint choice changes the architecture and the diagram. It answers:

  1. Does an unauthenticated GET to the Devpost hackathon search endpoint return data?
  2. What does one hackathon object actually look like?
  3. Which of those fields map onto src.state.Candidate, and which do not?

Usage:
    python verify_devpost.py [search query, default "singapore"]

Costs nothing, no credentials required. If this fails, do not spend time debugging a dead
endpoint: switch to the committed fixture fallback in PLAN.md section 10 (serve
data/fixtures/devpost_response.json, badge the source as prototype data in the UI, relabel the
diagram) and say so before building W2.3 around it.
"""

from __future__ import annotations

import json
import sys

import requests

from src.config import TOOL_TIMEOUT_SECONDS

SEARCH_URL = "https://devpost.com/api/hackathons"


def fail(message: str, hint: str = "") -> None:
    print(f"\n  FAILED: {message}")
    if hint:
        print(f"  {hint}")
    sys.exit(1)


def check_endpoint(query: str) -> dict:
    print(f"1. GET {SEARCH_URL}?search={query}")
    try:
        response = requests.get(
            SEARCH_URL, params={"search": query}, timeout=TOOL_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        fail(
            str(exc),
            "Endpoint is unreachable or rejected the request. Switch to the fixture\n"
            "  fallback in PLAN.md section 10 and say so before building W2.3.",
        )

    try:
        payload = response.json()
    except ValueError:
        fail("response was not JSON", "Devpost may have changed this endpoint's shape.")

    hackathons = payload.get("hackathons") or []
    if not hackathons:
        fail(
            f"no hackathons in response for query {query!r}",
            "Try a broader query. If every query comes back empty, treat this as a fail\n"
            "  and switch to the fixture fallback.",
        )

    print(f"   ok, {len(hackathons)} hackathons returned")
    return payload


def show_sample(payload: dict) -> dict:
    print("\n2. First hackathon, raw JSON (paste this into the group chat)")
    sample = payload["hackathons"][0]
    print(json.dumps(sample, indent=2))
    return sample


def show_candidate_mapping(sample: dict) -> None:
    print("\n3. Fields mapping onto src.state.Candidate")
    print(f"   id                -> f'devpost:{{h[\"id\"]}}'          = devpost:{sample.get('id')}")
    print("   kind              -> CandidateKind.HACKATHON  (constant, not from the API)")
    print("   source            -> SourceName.DEVPOST       (constant, not from the API)")
    print(f"   title             -> h['title']               = {sample.get('title')!r}")
    print(f"   url               -> h['url']                 = {sample.get('url')!r}")
    print(
        "   description       -> built from organization_name + themes, no raw 1:1 field"
        f" (organization_name={sample.get('organization_name')!r},"
        f" themes={[t.get('name') for t in sample.get('themes', [])]})"
    )
    print(
        f"   deadline          -> NOT parsed here. submission_period_dates is free text"
        f" ({sample.get('submission_period_dates')!r}); needs a real parser in W2.3, not"
        " solved by this script."
    )
    print("   time_cost_hours   -> config.TIME_COST_HOURS['hackathon'], not from the API")
    print("   closes_gaps       -> filled later by the model/scorer, not from raw data")
    print("   scores            -> filled later by the scorer, not from raw data")


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "singapore"
    print(f"Devpost endpoint preflight check, query={query!r}\n" + "-" * 50)
    payload = check_endpoint(query)
    sample = show_sample(payload)
    show_candidate_mapping(sample)

    print("\n" + "-" * 50)
    print("All checks passed. Devpost is a viable live source for W2.3.")


if __name__ == "__main__":
    main()
