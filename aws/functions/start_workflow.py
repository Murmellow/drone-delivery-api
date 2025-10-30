import json
import os
import boto3
from typing import Any

sf_client = boto3.client("stepfunctions")

STATE_MACHINE_ARN = os.getenv("STATE_MACHINE_ARN", "")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # Expect body JSON with fields referenced in the state machine (order_id, drone_id, etc.)
    body: dict[str, Any]
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except Exception:
            body = {}
    else:
        body = {}

    if not STATE_MACHINE_ARN:
        return {"statusCode": 500, "body": json.dumps({"detail": "STATE_MACHINE_ARN not configured"})}

    resp = sf_client.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps(body or {}),
    )
    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"executionArn": resp.get("executionArn")}),
    }
