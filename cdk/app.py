#!/usr/bin/env python3
"""CDK entry point for DevOptimally ECS Fargate deployment."""

import aws_cdk as cdk
from stack import DevOptimallyStack

app = cdk.App()

DevOptimallyStack(
    app,
    "DevOptimally",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-2",
    ),
    description="DevOptimally Agentic Cloud Optimizer - ECS Fargate",
)

app.synth()
