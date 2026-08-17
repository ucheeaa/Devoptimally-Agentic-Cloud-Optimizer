"""
Architecture Analysis Tool — real AWS APIs (EC2, RDS, ELB, CloudFront) with fallback.
"""

import json
from collections import defaultdict
from pathlib import Path

import boto3
from strands import tool


@tool
def analyze_architecture(environment_file: str = "data/sample_environment.json") -> str:
    """
    Analyze cloud architecture using live AWS API calls across EC2, RDS, ELB, and CloudFront.

    Discovers running resources, maps availability zone distribution, identifies
    single points of failure (services with only one instance), detects single-AZ
    deployments, and flags missing components such as load balancers, multi-AZ RDS,
    and CloudFront distributions. Falls back to sample JSON if APIs are unavailable.

    Args:
        environment_file: Path to fallback environment JSON.

    Returns:
        JSON string with topology_summary, single_points_of_failure, multi_az_gaps,
        missing_components, recommendations, and total_issues_found.
    """
    try:
        return _analyze_live_architecture()
    except Exception as exc:
        return _analyze_mock_architecture(environment_file, fallback_reason=str(exc))


def _analyze_live_architecture() -> str:
    region  = boto3.session.Session().region_name or "us-east-1"
    ec2_c   = boto3.client("ec2",         region_name=region)
    rds_c   = boto3.client("rds",         region_name=region)
    elb_c   = boto3.client("elbv2",       region_name=region)
    cf_c    = boto3.client("cloudfront",  region_name="us-east-1")  # CloudFront is global

    resources   = []
    az_map      = defaultdict(set)   # service → set of AZs
    service_map = defaultdict(list)  # service → list of resource dicts

    # EC2 instances
    ec2_resp = ec2_c.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    for res in ec2_resp["Reservations"]:
        for inst in res["Instances"]:
            az   = inst.get("Placement", {}).get("AvailabilityZone", "unknown")
            name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                        inst["InstanceId"])
            r = {"id": inst["InstanceId"], "name": name, "service": "ec2",
                 "instance_type": inst.get("InstanceType"), "az": az}
            resources.append(r)
            service_map["ec2"].append(r)
            az_map["ec2"].add(az)

    # RDS instances
    rds_resp = rds_c.describe_db_instances()
    for db in rds_resp.get("DBInstances", []):
        if db.get("DBInstanceStatus") != "available":
            continue
        az  = db.get("AvailabilityZone", "unknown")
        multi_az = db.get("MultiAZ", False)
        r = {"id": db["DBInstanceIdentifier"], "name": db["DBInstanceIdentifier"],
             "service": "rds", "instance_type": db.get("DBInstanceClass"),
             "az": az, "multi_az": multi_az}
        resources.append(r)
        service_map["rds"].append(r)
        az_map["rds"].add(az)

    # Load balancers
    elb_resp = elb_c.describe_load_balancers()
    for lb in elb_resp.get("LoadBalancers", []):
        if lb.get("State", {}).get("Code") != "active":
            continue
        azs = [az["ZoneName"] for az in lb.get("AvailabilityZones", [])]
        r = {"id": lb["LoadBalancerArn"], "name": lb["LoadBalancerName"],
             "service": "load_balancer", "type": lb.get("Type"), "azs": azs}
        resources.append(r)
        service_map["load_balancer"].append(r)
        for az in azs:
            az_map["load_balancer"].add(az)

    # CloudFront distributions
    cf_resp = cf_c.list_distributions()
    dist_list = cf_resp.get("DistributionList", {}).get("Items", [])
    for dist in dist_list:
        if dist.get("Status") != "Deployed":
            continue
        r = {"id": dist["Id"], "name": dist.get("DomainName", dist["Id"]),
             "service": "cdn"}
        resources.append(r)
        service_map["cdn"].append(r)

    # ── Analysis ──────────────────────────────────────────────────────────────

    # Single points of failure (EC2/RDS with only 1 instance)
    single_points_of_failure = []
    for svc in ["ec2", "rds"]:
        items = service_map.get(svc, [])
        if len(items) == 1:
            single_points_of_failure.append({
                "service": svc,
                "instance_count": 1,
                "risk": "No redundancy - a failure would cause a service outage.",
                "recommendation": f"Deploy at least 2 instances of '{svc}' behind a load balancer.",
                "priority": "High",
            })

    # Single-AZ deployments
    multi_az_gaps = []
    for svc, az_set in az_map.items():
        if svc in ("cdn", "load_balancer"):
            continue
        if len(az_set) < 2:
            multi_az_gaps.append({
                "service": svc,
                "availability_zones": sorted(az_set),
                "risk": "All instances in a single AZ.",
                "recommendation": f"Distribute '{svc}' across at least 2 AZs.",
                "priority": "High",
            })

    # RDS without Multi-AZ enabled
    for db in service_map.get("rds", []):
        if not db.get("multi_az"):
            multi_az_gaps.append({
                "service": "rds",
                "instance": db["name"],
                "risk": "RDS instance does not have Multi-AZ enabled.",
                "recommendation": "Enable Multi-AZ for automatic failover.",
                "priority": "High",
            })

    # Missing components
    missing_components = []
    if not service_map.get("load_balancer"):
        missing_components.append({
            "component": "load_balancer",
            "message": "No load balancer found. Add an ALB to distribute traffic and enable HA.",
            "priority": "High",
        })
    if not service_map.get("cdn"):
        missing_components.append({
            "component": "cdn",
            "message": "No CloudFront distribution found. A CDN reduces latency and origin load.",
            "priority": "Medium",
        })

    recommendations = (
        [{"type": "single_point_of_failure", **i} for i in single_points_of_failure]
        + [{"type": "multi_az_gap", **i} for i in multi_az_gaps]
        + [{"type": "missing_component", **i} for i in missing_components]
    )

    unique_azs = set()
    for az_set in az_map.values():
        unique_azs.update(az_set)
    if len(unique_azs) >= 3 and not single_points_of_failure:
        arch_rating = "Resilient"
    elif len(unique_azs) >= 2:
        arch_rating = "Multi-AZ"
    else:
        arch_rating = "Single-AZ"

    return json.dumps({
        "data_source": "AWS live APIs (EC2, RDS, ELBv2, CloudFront)",
        "topology_summary": {
            "total_resources": len(resources),
            "services": {k: len(v) for k, v in service_map.items()},
            "regions": [region],
            "architecture_rating": arch_rating,
        },
        "single_points_of_failure": single_points_of_failure,
        "multi_az_gaps": multi_az_gaps,
        "missing_components": missing_components,
        "recommendations": recommendations,
        "total_issues_found": len(recommendations),
    })


def _analyze_mock_architecture(environment_file: str, fallback_reason: str) -> str:
    env       = _load_environment(environment_file)
    resources = env.get("resources", [])
    metadata  = env.get("metadata", {})

    services  = defaultdict(list)
    az_map    = defaultdict(set)

    for resource in resources:
        svc = resource.get("service", "unknown")
        az  = resource.get("availability_zone", "unknown")
        services[svc].append(resource)
        az_map[svc].add(az)

    single_points_of_failure = [
        {"service": svc, "instance_count": len(lst),
         "risk": "No redundancy.", "priority": "High",
         "recommendation": f"Deploy at least 2 instances of '{svc}'."}
        for svc, lst in services.items() if len(lst) == 1
    ]
    multi_az_gaps = [
        {"service": svc, "availability_zones": sorted(az_set),
         "risk": "Single AZ deployment.", "priority": "High",
         "recommendation": f"Distribute '{svc}' across 2+ AZs."}
        for svc, az_set in az_map.items() if len(az_set) < 2
    ]
    expected = {
        "load_balancer": "No load balancer detected.",
        "cdn": "No CDN detected.",
        "database_replica": "No DB replica found.",
        "monitoring": "No monitoring resource found.",
    }
    missing_components = [
        {"component": c, "message": m, "priority": "Medium"}
        for c, m in expected.items()
        if not any(r.get("service", "").lower() == c for r in resources)
    ]

    recommendations = (
        [{"type": "single_point_of_failure", **i} for i in single_points_of_failure]
        + [{"type": "multi_az_gap", **i} for i in multi_az_gaps]
        + [{"type": "missing_component", **i} for i in missing_components]
    )

    unique_azs: set = set()
    for az_set in az_map.values():
        unique_azs.update(az_set)
    arch_rating = (
        "Resilient" if len(unique_azs) >= 3 and not single_points_of_failure
        else "Multi-AZ" if len(unique_azs) >= 2
        else "Single-AZ"
    )

    return json.dumps({
        "data_source": "sample data (fallback)",
        "fallback_reason": fallback_reason,
        "topology_summary": {
            "total_resources": len(resources),
            "services": {k: len(v) for k, v in services.items()},
            "architecture_rating": arch_rating,
            "environment_name": metadata.get("environment_name", "unknown"),
            "cloud_provider": metadata.get("cloud_provider", "unknown"),
        },
        "single_points_of_failure": single_points_of_failure,
        "multi_az_gaps": multi_az_gaps,
        "missing_components": missing_components,
        "recommendations": recommendations,
        "total_issues_found": len(recommendations),
    })


def _load_environment(path: str) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")
    with file_path.open() as f:
        return json.load(f)
