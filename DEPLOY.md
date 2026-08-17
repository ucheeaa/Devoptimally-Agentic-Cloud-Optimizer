# Deploying DevOptimally to AWS ECS Fargate

## Prerequisites

- AWS CLI configured (`aws login --region us-east-2`)
- Docker running locally
- Node.js installed (for CDK CLI)

## One-time setup

```bash
# Install CDK CLI
npm install -g aws-cdk

# Bootstrap CDK in your account (one-time per account/region)
cd cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$ACCOUNT_ID/us-east-2
```

## Deploy

```bash
cd cdk
source .venv/bin/activate

cdk deploy --context account=$ACCOUNT_ID --context region=us-east-2
```

CDK will:
1. Build and push the Docker image to ECR
2. Create a VPC, ECS cluster, and Fargate service
3. Provision an Application Load Balancer
4. Output a public URL

The deploy takes about 5-8 minutes. The URL will be printed at the end:

```
Outputs:
DevOptimally.AppUrl = http://DevOp-Servi-XXXX.us-east-2.elb.amazonaws.com
```

## Teardown

```bash
cdk destroy --context account=$ACCOUNT_ID --context region=us-east-2
```

## IAM permissions needed for deployment

Your AWS user/role needs:
- `AmazonECS_FullAccess`
- `AmazonEC2ContainerRegistryFullAccess`
- `AmazonVPCFullAccess`
- `ElasticLoadBalancingFullAccess`
- `IAMFullAccess`
- `CloudFormationFullAccess`
- `AmazonBedrockFullAccess`

Or attach `AdministratorAccess` for a hackathon.
