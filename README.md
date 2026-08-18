 # DevOptimally — Agentic Cloud Optimizer

An agentic AI system built on **Amazon Bedrock** (Claude Sonnet 4.5) and the **Strands Agents SDK** that autonomously analyzes cloud infrastructure and delivers a single prioritized cost, performance, and architecture recommendation through a clean Streamlit UI.

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Architecture](#architecture)
3. [File-by-File Breakdown](#file-by-file-breakdown)
4. [AWS Services Used](#aws-services-used)
5. [Docker](#docker)
6. [Running Locally](#running-locally)
7. [Deploy to AWS (ECS Fargate)](#deploy-to-aws-ecs-fargate)
8. [Environment Variables](#environment-variables)
9. [IAM Permissions](#iam-permissions)
10. [Room for Improvement](#room-for-improvement)

---

## How It Works

DevOptimally uses an **agentic loop** — the LLM decides which tools to call, in what order, and synthesizes the results into a single recommendation. You ask it a question; it autonomously gathers data from your AWS account and reasons over it.

```
User prompt
    │
    ▼
CloudOptimizerAgent  (Strands agentic loop + Claude Sonnet 4.5 via Bedrock)
    │
    ├── analyze_costs        → AWS Cost Explorer  (30-day spend by service, savings heuristics)
    ├── get_metrics          → AWS CloudWatch + EC2  (24-hr CPU/network per instance)
    └── analyze_architecture → EC2 + RDS + ELBv2 + CloudFront  (topology, SPOFs, AZ gaps)
                 │
                 └── fallback: data/sample_environment.json  (when live APIs unavailable)
    │
    ▼
Structured JSON recommendation
    │
    ▼
Streamlit UI  (card-based dashboard, evidence, alternatives)
```

The agent is instructed (via `agent/prompts.py`) to call **all three tools** before drawing any conclusion, then return a single JSON object — no prose, no markdown fences — that the UI parses and renders into metric cards, a recommendation panel, and expandable evidence/alternatives sections.

---

## Architecture

```
devoptimally/
│
├── ui.py                         # Streamlit frontend
│   └── run_agent()               # spins up CloudOptimizerAgent, collects step events
│
├── app.py                        # CLI entry point (no Streamlit required)
│
├── agent/
│   ├── agent.py                  # CloudOptimizerAgent wrapper + build_agent()
│   └── prompts.py                # SYSTEM_PROMPT — task framing + JSON output contract
│
├── tools/
│   ├── cost_tool.py              # @tool analyze_costs
│   ├── metrics_tool.py           # @tool get_metrics
│   └── architecture_tool.py     # @tool analyze_architecture
│
├── data/
│   └── sample_environment.json  # 8-resource mock AWS environment (fallback)
│
├── Dockerfile                    # Multi-stage image; runs streamlit run ui.py
├── cdk/
│   ├── app.py                    # CDK app entry point
│   └── stack.py                  # DevOptimallyStack: VPC + ECS Fargate + ALB
│
├── iam-policy.json               # Least-privilege IAM policy for the optimizer
├── requirements.txt              # Python dependencies
└── .env.example                  # Env var template
```

---

## File-by-File Breakdown

### `ui.py` — Streamlit UI

The browser interface. Renders a dark-themed, card-based dashboard built entirely with `st.markdown` + custom CSS (Inter font, GitHub-dark palette). Key responsibilities:

- Renders the **environment summary** card (monthly cost, compute utilization, architecture rating) populated from the agent's JSON output.
- Hosts the **Ask DevOptimally** text area and suggestion pills that pre-populate the prompt.
- On "Analyze" click, calls `run_agent()` in a `st.spinner` block, then `st.rerun()` to re-render with results.
- Renders the **Agent Investigation** progress card (four steps: inspected architecture, retrieved utilization metrics, analyzed cost breakdown, evaluated optimization options) — steps are marked done as tool-call events fire via the `on_tool_call` callback.
- Renders the **Recommendation** card with monthly savings, risk badge, explanation, and collapsible evidence/alternatives expanders.
- Falls back to a raw `<pre>` block if the agent response is not valid JSON.

### `app.py` — CLI Entry Point

A minimal terminal interface for running the agent without Streamlit. Instantiates `CloudOptimizerAgent` with a simple `print`-based `on_tool_call` callback, runs the default optimization task, and pretty-prints the JSON result. Useful for testing the agent loop in CI or a plain terminal.

### `agent/agent.py` — Agent Core

Two exports:

- **`build_agent(callback_handler)`** — constructs a `strands.Agent` with a `BedrockModel` pointing at `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (overridable via `BEDROCK_MODEL_ID`), `temperature=0.3`, the system prompt from `prompts.py`, and the three tool functions registered as Strands tools.
- **`CloudOptimizerAgent`** — a thin wrapper that wires a `callback_handler` into the Strands event stream to intercept `current_tool_use` events, deduplicate consecutive tool names, populate `self.tool_calls`, and forward each unique tool name to the optional `on_tool_call` callback. `run(task)` prepends the environment file path to the task string so the tools receive it automatically, then returns `{raw_response, tool_calls}`.

### `agent/prompts.py` — System Prompt

Defines `SYSTEM_PROMPT` — the instruction contract given to Claude at session start. It:

- Names and describes each tool.
- Mandates that the agent call **all three tools** before synthesizing.
- Specifies the exact JSON output schema: `summary` (environment name, total cost, avg utilization, architecture rating) + `recommendation` (title, monthly savings, risk level, explanation, evidence bullets, alternatives array) + `agent_steps`.
- Forbids any text outside the JSON object, which makes the UI's `json.loads` parsing reliable.

### `tools/cost_tool.py` — `analyze_costs`

A Strands `@tool` that queries **AWS Cost Explorer** for the last 30 days of `UnblendedCost` grouped by service. It:

- Strips zero-cost services, returns the top-5 cost drivers.
- Applies simple heuristics to surface savings opportunities: EC2 over $50/mo → right-size or Savings Plan (est. 25% saving); RDS over $30/mo → Reserved Instances (30%); S3 over $10/mo → Intelligent-Tiering (20%).
- Falls back to `_analyze_mock_costs()` on any exception (no credentials, access denied, throttle). The fallback reads `sample_environment.json`, sums `monthly_cost_usd` per service, and flags resources with CPU < 5% and memory < 5% as idle (full cost saving) or CPU < 20% and memory < 30% as right-size candidates (50% saving).

### `tools/metrics_tool.py` — `get_metrics`

A Strands `@tool` that paginates `ec2:DescribeInstances` for all running instances, then calls `cloudwatch:GetMetricStatistics` for `CPUUtilization` and `NetworkIn` over the last 24 hours at 1-hour resolution. It:

- Averages the data points per instance and flags underutilized (avg CPU < 20%) and overutilized (avg CPU > 80%) resources.
- Falls back to `_get_mock_metrics()` which reads `sample_environment.json` and applies the same thresholds against the static utilization values.

### `tools/architecture_tool.py` — `analyze_architecture`

A Strands `@tool` that calls four AWS APIs in sequence:

- `ec2:DescribeInstances` — running instances, AZ placement, instance type.
- `rds:DescribeDBInstances` — available DB instances, AZ, Multi-AZ flag.
- `elbv2:DescribeLoadBalancers` — active load balancers, AZ coverage.
- `cloudfront:ListDistributions` — deployed CDN distributions (always `us-east-1` because CloudFront is a global service).

It then identifies:
- **Single points of failure** — any service (EC2 or RDS) with only one instance.
- **Multi-AZ gaps** — services deployed to fewer than two AZs, and RDS instances without `MultiAZ: true`.
- **Missing components** — no load balancer, no CloudFront distribution.

Produces an `architecture_rating` of `Single-AZ`, `Multi-AZ`, or `Resilient` (3+ AZs, no SPOFs). Falls back to `_analyze_mock_architecture()` which applies the same logic against `sample_environment.json`.

### `data/sample_environment.json` — Fallback Dataset

An 8-resource mock production environment:

| Resource | Service | Instance Type | Monthly Cost | CPU % |
|---|---|---|---|---|
| web-server-01 | EC2 | m5.2xlarge | $280 | 12% |
| api-server-01 | EC2 | m5.xlarge | $140 | 72% |
| batch-worker-01 | EC2 | c5.4xlarge | $490 | 3% |
| primary-rds | RDS | db.r5.2xlarge | $620 | 35% |
| assets-bucket | S3 | — | $95 | — |
| image-resize-fn | Lambda | 128 MB | $18 | 15% |
| app-cluster | EKS | t3.large (x3) | $350 | 88% |
| session-cache | ElastiCache | cache.t3.medium | $52 | 8% |

Total: ~$2,045/mo. The batch-worker (3% CPU, 2% memory on a c5.4xlarge at $490/mo) is the obvious right-size/terminate target the agent surfaces.

### `Dockerfile` — Container Image

See [Docker](#docker) section below.

### `cdk/stack.py` — Infrastructure as Code

See [Deploy to AWS](#deploy-to-aws-ecs-fargate) section below.

### `iam-policy.json` — Least-Privilege IAM Policy

A standalone JSON policy covering the minimum permissions the optimizer needs: Cost Explorer read, CloudWatch metrics read, EC2/RDS/ELB/CloudFront describe-only, Bedrock invoke, and ECR pull. Attach to a user or role when running outside of ECS. The CDK stack inlines equivalent `PolicyStatement` blocks into the task role automatically.

---

## AWS Services Used

| Service | How it is used |
|---|---|
| **Amazon Bedrock** | Hosts Claude Sonnet 4.5. The agent uses the `Converse` / `ConverseStream` API via the Strands SDK `BedrockModel`. Requires model access to be enabled in the Bedrock console. |
| **AWS Cost Explorer** | `ce:GetCostAndUsage` — 30-day spend grouped by service. Always routed through `us-east-1` (Cost Explorer is a global service endpoint). |
| **Amazon CloudWatch** | `cloudwatch:GetMetricStatistics` — `CPUUtilization` and `NetworkIn` for each running EC2 instance over a 24-hour window at 1-hour resolution. |
| **Amazon EC2** | `ec2:DescribeInstances` — enumerates running instances for the metrics and architecture tools. |
| **Amazon RDS** | `rds:DescribeDBInstances` — lists available DB instances, checks `MultiAZ` flag, maps AZ placement. |
| **Elastic Load Balancing (ELBv2)** | `elbv2:DescribeLoadBalancers` — detects active ALB/NLB and their AZ spread. |
| **Amazon CloudFront** | `cloudfront:ListDistributions` — checks whether a CDN layer exists. |
| **Amazon ECS Fargate** | Runtime for the containerized Streamlit app when deployed via CDK. The CDK stack provisions the task definition, service, and ALB. |
| **Amazon ECR** | CDK `DockerImageAsset` builds the image locally and pushes it to an auto-created ECR repository during `cdk deploy`. |
| **Amazon VPC** | CDK creates a dedicated VPC with 2 AZs and 1 NAT gateway for the Fargate service. |
| **AWS CloudFormation** | CDK synthesizes and deploys the stack as a CloudFormation template. |
| **Amazon CloudWatch Logs** | Fargate task logs stream to `/devoptimally/app` with 1-week retention (configured in the CDK stack). |

---

## Docker

The `Dockerfile` uses a **two-stage build** to keep the runtime image small:

```
Stage 1 — builder  (python:3.11-slim)
  COPY requirements.txt
  RUN pip install --prefix=/install -r requirements.txt
  # installs into /install; not into the image's site-packages

Stage 2 — runtime  (python:3.11-slim)
  COPY --from=builder /install /usr/local   # only the installed packages
  COPY . .                                  # application source
  ENV PYTHONUNBUFFERED=1
  ENV STREAMLIT_SERVER_PORT=8501
  ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
  EXPOSE 8501
  ENTRYPOINT ["streamlit", "run", "ui.py", "--server.headless=true"]
```

**Build and run locally:**

```bash
docker build -t devoptimally .

# Pass credentials via env file — never bake secrets into the image
docker run --env-file .env -p 8501:8501 devoptimally
```

Open http://localhost:8501

AWS credentials are injected at runtime via `--env-file .env` (or `-e` flags). When deployed on ECS Fargate the task role provides credentials automatically — no env vars needed for auth.

---

## Running Locally

### Prerequisites

- Python 3.11+
- AWS credentials configured with Cost Explorer, CloudWatch, EC2, RDS, ELBv2, and CloudFront read access, plus Bedrock invoke access (see `iam-policy.json`).
- Bedrock model access enabled: AWS Console → Amazon Bedrock → Model access → enable **Claude Sonnet 4.5** (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`).

### 1. Clone and install

```bash
git clone <repo-url>
cd devoptimally

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`botocore[crt]` is included in `requirements.txt` to enable the optional AWS Common Runtime (CRT) HTTP client, which improves S3 and multipart performance and is required by some Strands SDK features.

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env — set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
# Or skip this step if you have run: aws configure
```

If you have valid AWS credentials, the tools will query live Cost Explorer, CloudWatch, EC2, RDS, ELBv2, and CloudFront data. If any API call fails (no credentials, insufficient permissions, empty account), the tool automatically falls back to `data/sample_environment.json` — no configuration change needed.

### 3. Run the Streamlit UI

```bash
streamlit run ui.py
```

Open http://localhost:8501. Type a question or click a suggestion pill, then hit **Analyze**. The agent will call all three tools and render a recommendation.

### 4. Run the CLI (optional)

```bash
python app.py
```

Runs the default task ("Find the safest way to reduce our cloud cost") and prints the JSON recommendation to stdout.

---

## Deploy to AWS (ECS Fargate)

Full step-by-step instructions are in [`DEPLOY.md`](DEPLOY.md). Summary:

```bash
# One-time CDK bootstrap
npm install -g aws-cdk
cd cdk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$ACCOUNT_ID/us-east-2

# Deploy
cdk deploy --context account=$ACCOUNT_ID --context region=us-east-2
```

CDK creates:
- **VPC** with 2 AZs, 1 NAT gateway.
- **ECS cluster** with Container Insights enabled.
- **ECR repository** — image built and pushed automatically via `DockerImageAsset`.
- **Fargate service** (0.5 vCPU / 1 GB) with desired count 1.
- **Application Load Balancer** — public, health check on `/_stcore/health`.
- **IAM task role** with the least-privilege policy for all optimizer APIs and Bedrock.
- **CloudWatch log group** `/devoptimally/app` (1-week retention).

The public URL is printed as a stack output. Teardown: `cdk destroy`.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | Yes* | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes* | — | AWS secret key |
| `AWS_REGION` | No | `us-east-1` | Region for CloudWatch, EC2, RDS, ELBv2 queries |
| `BEDROCK_MODEL_ID` | No | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Bedrock model ID |

*Not required when using `aws configure`, an IAM role, or ECS task role.

---

## IAM Permissions

The minimum permissions required are defined in `iam-policy.json`. Attach it to your IAM user or role:

```bash
aws iam put-user-policy \
  --user-name <your-user> \
  --policy-name DevOptimallyPolicy \
  --policy-document file://iam-policy.json
```

Permissions breakdown:

| Scope | Actions |
|---|---|
| Cost Explorer | `ce:GetCostAndUsage`, `ce:GetCostForecast`, `ce:GetDimensionValues` |
| CloudWatch | `cloudwatch:GetMetricStatistics`, `ListMetrics`, `GetMetricData` |
| EC2 | `ec2:DescribeInstances`, `DescribeRegions`, `DescribeAvailabilityZones`, `DescribeInstanceTypes` |
| RDS | `rds:DescribeDBInstances`, `DescribeDBClusters` |
| ELBv2 | `elasticloadbalancing:DescribeLoadBalancers`, `DescribeTargetGroups` |
| CloudFront | `cloudfront:ListDistributions` |
| Bedrock | `bedrock:InvokeModel`, `InvokeModelWithResponseStream`, `Converse`, `ConverseStream` |
| ECR | Pull-only (`GetAuthorizationToken`, `BatchCheckLayerAvailability`, etc.) |

---

## Room for Improvement

### More data sources
- **Lambda and ECS/EKS metrics** — `get_metrics` currently only queries EC2 instances. Adding `AWS/Lambda` and container-level CloudWatch namespaces would cover the full cost surface.
- **Trusted Advisor / Compute Optimizer integration** — surface AWS-native rightsizing recommendations as additional evidence.
- **AWS Config / Resource Groups Tagging API** — enumerate resources across all services rather than per-service describe calls.

### Richer cost analysis
- **Cost allocation tags** — break costs down by team, environment, or feature rather than just by service.
- **Savings Plans and Reserved Instance coverage** — `ce:GetSavingsPlansCoverage` and `ce:GetReservationCoverage` would let the agent quantify coverage gaps.
- **Forecasting** — `ce:GetCostForecast` is already in the IAM policy; wiring it in would let the agent project spend trends.

### Multi-account and multi-region
- The tools currently target a single AWS account and region. Adding AWS Organizations support (`organizations:ListAccounts`) and looping over regions would make it useful for enterprise environments.

### Agent improvements
- **Streaming UI** — the Strands callback already fires per tool call; extending it to stream partial text output would improve perceived responsiveness.
- **Memory / session history** — right now each run starts fresh. Persisting prior recommendations in DynamoDB or a session store would let the agent track whether previous suggestions were acted on.
- **Confidence scoring** — the agent could tag each recommendation with a confidence level based on data completeness (live vs. fallback).
- **Automated remediation** — low-risk actions (stopping idle instances, enabling S3 Intelligent-Tiering) could be offered as one-click actions with a confirmation step, using EC2/S3 write permissions scoped behind an approval gate.

### Infrastructure
- **HTTPS on the ALB** — the CDK stack currently uses HTTP. Adding an ACM certificate and a `CfnListenerRule` for HTTPS would be production-ready.
- **Auto Scaling** — the Fargate service runs at `desired_count=1`. Adding a `ScalableTarget` on CPU utilization would handle traffic spikes.
- **Secrets Manager** — AWS credentials passed as environment variables should be stored in Secrets Manager and resolved at task launch using the `{{resolve:secretsmanager:...}}` syntax.
