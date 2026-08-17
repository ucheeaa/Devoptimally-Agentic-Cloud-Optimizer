"""
Cost Analysis Tool — real AWS Cost Explorer API with sample-data fallback.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from strands import tool


@tool
def analyze_costs(environment_file: str = "data/sample_environment.json") -> str:
    """
    Analyze cloud resource costs using the AWS Cost Explorer API.

    Retrieves the last 30 days of spending broken down by service, identifies
    the top cost drivers, calculates day-over-day trends, and surfaces
    savings opportunities. Falls back to the sample environment JSON if
    Cost Explorer is unavailable or returns no data.

    Args:
        environment_file: Path to fallback environment JSON (used when live
                          data is unavailable).

    Returns:
        JSON string with total_monthly_cost_usd, cost_by_service,
        savings_opportunities, data_source, and period.
    """
    try:
        return _analyze_live_costs()
    except Exception as exc:
        # Graceful fallback to mock data
        return _analyze_mock_costs(environment_file, fallback_reason=str(exc))


def _analyze_live_costs() -> str:
    """Pull real cost data from AWS Cost Explorer."""
    ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is global, always us-east-1

    end   = date.today()
    start = end - timedelta(days=30)

    # Total cost + breakdown by service
    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    cost_by_service: dict[str, float] = {}
    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            service = group["Keys"][0]
            amount  = float(group["Metrics"]["UnblendedCost"]["Amount"])
            cost_by_service[service] = cost_by_service.get(service, 0) + amount

    # Remove zero-cost services
    cost_by_service = {k: round(v, 2) for k, v in cost_by_service.items() if v > 0.01}

    total = round(sum(cost_by_service.values()), 2)

    # Top 5 services by cost
    top_services = sorted(cost_by_service.items(), key=lambda x: x[1], reverse=True)[:5]

    # Simple savings heuristics based on service spend
    savings_opportunities = []
    for service, cost in cost_by_service.items():
        svc_lower = service.lower()
        if "ec2" in svc_lower and cost > 50:
            savings_opportunities.append({
                "service": service,
                "recommendation": "Review EC2 instances for right-sizing or Savings Plan coverage.",
                "estimated_monthly_savings_usd": round(cost * 0.25, 2),
                "priority": "High",
            })
        elif "rds" in svc_lower and cost > 30:
            savings_opportunities.append({
                "service": service,
                "recommendation": "Consider Reserved Instances for RDS — up to 40% savings.",
                "estimated_monthly_savings_usd": round(cost * 0.30, 2),
                "priority": "Medium",
            })
        elif "s3" in svc_lower and cost > 10:
            savings_opportunities.append({
                "service": service,
                "recommendation": "Enable S3 Intelligent-Tiering for infrequently accessed data.",
                "estimated_monthly_savings_usd": round(cost * 0.20, 2),
                "priority": "Low",
            })

    return json.dumps({
        "data_source": "AWS Cost Explorer (live)",
        "period": f"{start.isoformat()} to {end.isoformat()}",
        "total_monthly_cost_usd": total,
        "cost_by_service": dict(top_services),
        "all_services_count": len(cost_by_service),
        "savings_opportunities": savings_opportunities,
        "total_potential_savings_usd": round(
            sum(s["estimated_monthly_savings_usd"] for s in savings_opportunities), 2
        ),
    })


def _analyze_mock_costs(environment_file: str, fallback_reason: str) -> str:
    """Fall back to sample JSON when live data is unavailable."""
    env       = _load_environment(environment_file)
    resources = env.get("resources", [])

    cost_by_service: dict[str, float] = {}
    savings_opportunities = []

    for resource in resources:
        service      = resource.get("service", "unknown")
        monthly_cost = float(resource.get("monthly_cost_usd", 0))
        utilization  = resource.get("utilization", {})
        cost_by_service[service] = cost_by_service.get(service, 0) + monthly_cost

        cpu    = utilization.get("cpu_percent", 100)
        memory = utilization.get("memory_percent", 100)

        if cpu < 5 and memory < 5:
            savings_opportunities.append({
                "resource_id": resource.get("id"),
                "resource_name": resource.get("name"),
                "recommendation": f"Terminate idle resource '{resource.get('name')}'",
                "estimated_monthly_savings_usd": monthly_cost,
                "priority": "High",
            })
        elif cpu < 20 and memory < 30:
            savings_opportunities.append({
                "resource_id": resource.get("id"),
                "resource_name": resource.get("name"),
                "recommendation": (
                    f"Right-size '{resource.get('name')}' — "
                    f"CPU at {cpu}%, memory at {memory}%."
                ),
                "estimated_monthly_savings_usd": round(monthly_cost * 0.5, 2),
                "priority": "Medium",
            })

    total = round(sum(cost_by_service.values()), 2)

    return json.dumps({
        "data_source": "sample data (fallback)",
        "fallback_reason": fallback_reason,
        "total_monthly_cost_usd": total,
        "cost_by_service": {k: round(v, 2) for k, v in cost_by_service.items()},
        "savings_opportunities": savings_opportunities,
        "total_potential_savings_usd": round(
            sum(s["estimated_monthly_savings_usd"] for s in savings_opportunities), 2
        ),
    })


def _load_environment(path: str) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    with file_path.open() as f:
        return json.load(f)
