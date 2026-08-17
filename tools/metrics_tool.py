"""
Metrics Tool — real CloudWatch + EC2 APIs with sample-data fallback.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from strands import tool

# CloudWatch metric period (seconds) and stat
_PERIOD   = 3600        # 1-hour resolution
_STAT     = "Average"
_LOOKBACK = 24          # hours of history to average


@tool
def get_metrics(environment_file: str = "data/sample_environment.json") -> str:
    """
    Retrieve CPU and network utilization metrics for EC2 instances using CloudWatch.

    Queries the last 24 hours of Average CPUUtilization and NetworkIn metrics
    for all running EC2 instances in the account. Also identifies underutilized
    instances (avg CPU below 20%) and overutilized instances (avg CPU above 80%).
    Falls back to the sample environment JSON if CloudWatch is unavailable.

    Args:
        environment_file: Path to fallback environment JSON.

    Returns:
        JSON string with resource_metrics, underutilized, overutilized,
        summary, and data_source.
    """
    try:
        return _get_live_metrics()
    except Exception as exc:
        return _get_mock_metrics(environment_file, fallback_reason=str(exc))


def _get_live_metrics() -> str:
    region = boto3.session.Session().region_name or "us-east-1"
    ec2 = boto3.client("ec2", region_name=region)
    cw  = boto3.client("cloudwatch", region_name=region)

    # List running EC2 instances
    paginator = ec2.get_paginator("describe_instances")
    instances = []
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                name = next(
                    (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                    inst["InstanceId"],
                )
                instances.append({
                    "id":            inst["InstanceId"],
                    "name":          name,
                    "instance_type": inst.get("InstanceType", "unknown"),
                    "az":            inst.get("Placement", {}).get("AvailabilityZone", "unknown"),
                })

    if not instances:
        return json.dumps({
            "data_source": "AWS CloudWatch (live)",
            "message": "No running EC2 instances found in this account.",
            "resource_metrics": [],
            "underutilized": [],
            "overutilized": [],
            "summary": {"total_resources": 0},
        })

    end_time   = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=_LOOKBACK)

    resource_metrics = []
    underutilized    = []
    overutilized     = []
    cpu_values       = []

    for inst in instances:
        iid = inst["id"]

        def _get_metric(metric_name, namespace="AWS/EC2"):
            resp = cw.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[{"Name": "InstanceId", "Value": iid}],
                StartTime=start_time,
                EndTime=end_time,
                Period=_PERIOD,
                Statistics=[_STAT],
            )
            points = resp.get("Datapoints", [])
            if not points:
                return 0.0
            return round(sum(p[_STAT] for p in points) / len(points), 2)

        cpu     = _get_metric("CPUUtilization")
        net_in  = _get_metric("NetworkIn")     # bytes
        net_mbps = round(net_in / 1_000_000, 2)

        entry = {
            "id":            iid,
            "name":          inst["name"],
            "service":       "ec2",
            "instance_type": inst["instance_type"],
            "availability_zone": inst["az"],
            "cpu_percent":   cpu,
            "network_mbps":  net_mbps,
        }
        resource_metrics.append(entry)
        cpu_values.append(cpu)

        if cpu < 20:
            underutilized.append({
                **entry,
                "recommendation": "Consider right-sizing to a smaller instance type.",
            })
        if cpu > 80:
            overutilized.append({
                **entry,
                "recommendation": "Instance under strain. Consider scaling up or using Auto Scaling.",
            })

    avg_cpu = round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0

    return json.dumps({
        "data_source": "AWS CloudWatch (live)",
        "lookback_hours": _LOOKBACK,
        "resource_metrics": resource_metrics,
        "underutilized": underutilized,
        "overutilized": overutilized,
        "summary": {
            "total_resources":     len(instances),
            "avg_cpu_percent":     avg_cpu,
            "underutilized_count": len(underutilized),
            "overutilized_count":  len(overutilized),
        },
    })


def _get_mock_metrics(environment_file: str, fallback_reason: str) -> str:
    env       = _load_environment(environment_file)
    resources = env.get("resources", [])

    resource_metrics = []
    underutilized    = []
    overutilized     = []
    cpu_values       = []

    for resource in resources:
        util = resource.get("utilization", {})
        cpu  = util.get("cpu_percent", 0)
        entry = {
            "id":            resource.get("id"),
            "name":          resource.get("name"),
            "service":       resource.get("service"),
            "instance_type": resource.get("instance_type"),
            "cpu_percent":   cpu,
            "memory_percent": util.get("memory_percent", 0),
            "network_mbps":  util.get("network_mbps", 0),
            "monthly_cost_usd": resource.get("monthly_cost_usd", 0),
        }
        resource_metrics.append(entry)
        cpu_values.append(cpu)

        if cpu < 20 and util.get("memory_percent", 100) < 40:
            underutilized.append({**entry, "recommendation": "Consider right-sizing."})
        if cpu > 80 or util.get("memory_percent", 0) > 85:
            overutilized.append({**entry, "recommendation": "Resource under strain."})

    compute = [r for r in resources if r.get("service") in {"ec2", "eks", "ecs"}]
    compute_cpu = [r.get("utilization", {}).get("cpu_percent", 0) for r in compute]
    avg_compute = round(sum(compute_cpu) / len(compute_cpu), 2) if compute_cpu else 0

    return json.dumps({
        "data_source": "sample data (fallback)",
        "fallback_reason": fallback_reason,
        "resource_metrics": resource_metrics,
        "underutilized": underutilized,
        "overutilized": overutilized,
        "summary": {
            "total_resources":        len(resources),
            "avg_cpu_percent":        round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0,
            "avg_compute_cpu_percent": avg_compute,
            "underutilized_count":    len(underutilized),
            "overutilized_count":     len(overutilized),
        },
    })


def _load_environment(path: str) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    with file_path.open() as f:
        return json.load(f)
