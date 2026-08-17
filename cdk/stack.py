"""
DevOptimally CDK Stack
Deploys the Streamlit app to ECS Fargate with a public ALB.
"""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct
import os


class DevOptimallyStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC ───────────────────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,
        )

        # ── ECS Cluster ───────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        # ── Docker image from local source ────────────────────────────────────
        image_asset = ecr_assets.DockerImageAsset(
            self,
            "AppImage",
            directory=os.path.join(os.path.dirname(__file__), ".."),
        )

        # ── IAM Task Role ─────────────────────────────────────────────────────
        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="DevOptimally ECS task role - read-only AWS access + Bedrock",
        )

        # Attach the optimizer permissions
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="CostExplorer",
                effect=iam.Effect.ALLOW,
                actions=[
                    "ce:GetCostAndUsage",
                    "ce:GetCostForecast",
                    "ce:GetDimensionValues",
                ],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatch",
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:ListMetrics",
                    "cloudwatch:GetMetricData",
                ],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="EC2RDSReadOnly",
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeInstances",
                    "ec2:DescribeRegions",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeInstanceTypes",
                    "rds:DescribeDBInstances",
                    "rds:DescribeDBClusters",
                    "elasticloadbalancing:DescribeLoadBalancers",
                    "elasticloadbalancing:DescribeTargetGroups",
                    "cloudfront:ListDistributions",
                ],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="Bedrock",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                ],
                resources=["*"],
            )
        )

        # ── CloudWatch Log Group ──────────────────────────────────────────────
        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name="/devoptimally/app",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ── Fargate Service with ALB ──────────────────────────────────────────
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(image_asset),
                container_port=8501,
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="devoptimally",
                    log_group=log_group,
                ),
                environment={
                    "AWS_REGION": self.region,
                    "BEDROCK_MODEL_ID": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "STREAMLIT_SERVER_PORT": "8501",
                    "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
                    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
                },
            ),
            public_load_balancer=True,
        )

        # Health check for Streamlit
        fargate_service.target_group.configure_health_check(
            path="/_stcore/health",
            healthy_http_codes="200",
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "AppUrl",
            value=f"http://{fargate_service.load_balancer.load_balancer_dns_name}",
            description="DevOptimally public URL",
        )
        cdk.CfnOutput(
            self,
            "LogGroupName",
            value=log_group.log_group_name,
            description="CloudWatch log group for the app",
        )
