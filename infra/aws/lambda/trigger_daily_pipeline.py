"""
EventBridge Scheduler → Lambda → SSM Run Command na EC2.

Uruchamia run_daily_pipeline.sh raz dziennie. Koszt: ~0 w free tier
(1 wywołanie Lambda/dzień + EventBridge Scheduler + SSM).
"""

from __future__ import annotations

import os

import boto3


def lambda_handler(event, context):
    instance_id = os.environ["EC2_INSTANCE_ID"]
    run_user = os.environ.get("RUN_AS_USER", "ubuntu")
    script = os.environ.get(
        "PIPELINE_SCRIPT",
        "/home/ubuntu/Job_search/infra/aws/run_daily_pipeline.sh",
    )

    commands = [
        f"sudo -u {run_user} -H bash -lc '{script}'",
    ]

    ssm = boto3.client("ssm")
    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands},
        TimeoutSeconds=3600,
        Comment="Job Search daily pipeline (EventBridge)",
    )

    command_id = response["Command"]["CommandId"]
    print(f"SSM command started: {command_id} on {instance_id}")

    return {
        "statusCode": 200,
        "instanceId": instance_id,
        "commandId": command_id,
    }
