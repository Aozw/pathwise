"""AgentCore Runtime entrypoint — W4.1.

Stub only: no graph invocation yet. This exists so the deploy path (AgentCore
Runtime locally, then the Lambda Function URL + S3 page in front of it) has
something real to point at from hour one. W4.4 replaces the body of `invoke`
with a real call into `src.graph.graph`.

Run locally:
    python src/entrypoint.py
    curl -X POST localhost:8080/invocations -d '{"prompt": "test"}'
"""

from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Stub handler. `payload` is the raw JSON body of the request, unvalidated."""
    return {
        "status": "ok",
        "message": "Pathwise entrypoint stub — graph not wired yet (W4.4)",
        "received": payload,
    }


if __name__ == "__main__":
    app.run()
