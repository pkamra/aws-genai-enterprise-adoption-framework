#!/bin/bash

# Provide your own parameter values for AWS region, CloudFormation stack name, CodePipeline pipeline name, and SNS email
export AWS_REGION="us-east-1"
export STACK_NAME="lambda-pipeline"
export CODEPIPELINE_NAME="lambda-pipeline"

# Below parameter values acquired from 'Gather Private Internal Repository Configuration' and 'Create GitHub Personal Access Token' pre-deployment
export PRIVATE_GITHUB_PAT=<YOUR-GITHUB-PAT>
export PRIVATE_GITHUB_OWNER=<YOUR-PRIVATE-REPOSITORY-OWNER>
export PRIVATE_GITHUB_REPO=<YOUR-PRIVATE-REPOSITORY-NAME>
export PRIVATE_GITHUB_BRANCH=<YOUR-PRIVATE-REPOSITORY-BRANCH>

# Below parameter values acquired from 'Configure VPC Networking' pre-deployment
export CODESERVICES_VPC_ID=<YOUR-VPC-ID>
export CODESERVICES_SUBNET_ID1=<YOUR-PRIVATE-SUBNET-ID-1>
export CODESERVICES_SUBNET_ID2=<YOUR-PRIVATE-SUBNET-ID-2>

# Other required parameters
export DOCKERFILE_NAME="lambda.dockerfile"
export DOCKER_IMAGE_NAME="office-converter-image"
export ECR_NAME="office-converter-image-registry"

# Generate a unique identifier for resources
export UNIQUE_IDENTIFIER=$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-' | cut -c 1-5)

# Create a secret in AWS Secrets Manager for the GitHub personal access token
export PRIVATE_GITHUB_TOKEN_SECRET_NAME=$(aws secretsmanager create-secret --name $STACK_NAME-$UNIQUE_IDENTIFIER-git-pat --secret-string $PRIVATE_GITHUB_PAT --region $AWS_REGION --query Name --output text)

# Create an S3 bucket for storing CodePipeline artifacts
export S3_ARTIFACTS_BUCKET_NAME=$STACK_NAME-pipeline-artifacts-$UNIQUE_IDENTIFIER
aws s3 mb s3://$S3_ARTIFACTS_BUCKET_NAME --region $AWS_REGION

# Create an S3 bucket for storing CodePipeline artifacts
export LAMBDA_SOURCE_BUCKET_NAME=$STACK_NAME-office-converter-source-$UNIQUE_IDENTIFIER
aws s3 mb s3://$LAMBDA_SOURCE_BUCKET_NAME --region $AWS_REGION

# Create the CloudFormation stack
aws cloudformation create-stack \
--stack-name $STACK_NAME \
--template-body file://../cfn/codeartifact-private-repo.yaml \
--parameters \
ParameterKey=S3ArtifactsBucket,ParameterValue=$S3_ARTIFACTS_BUCKET_NAME \
ParameterKey=CodePipelineName,ParameterValue=$CODEPIPELINE_NAME \
ParameterKey=PrivateGitHubBranch,ParameterValue=$PRIVATE_GITHUB_BRANCH \
ParameterKey=PrivateGitHubOwner,ParameterValue=$PRIVATE_GITHUB_OWNER \
ParameterKey=PrivateGitHubRepo,ParameterValue=$PRIVATE_GITHUB_REPO \
ParameterKey=PrivateGitHubToken,ParameterValue=$PRIVATE_GITHUB_TOKEN_SECRET_NAME \
ParameterKey=CodeServicesVpc,ParameterValue=$CODESERVICES_VPC_ID \
ParameterKey=CodeServicesSubnet,ParameterValue=$CODESERVICES_SUBNET_ID1\\,$CODESERVICES_SUBNET_ID2 \
ParameterKey=DockerfileName,ParameterValue=$DOCKERFILE_NAME \
ParameterKey=DockerImageName,ParameterValue=$DOCKER_IMAGE_NAME \
ParameterKey=ECRName,ParameterValue=$ECR_NAME \
ParameterKey=LambdaSourceBucket,ParameterValue=$LAMBDA_SOURCE_BUCKET_NAME \
--capabilities CAPABILITY_IAM \
--region $AWS_REGION 

# Check the deployment status of the CloudFormation stack
echo "Checking stack deployment status..."
aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus"
echo "Waiting for stack creation to complete..."
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $AWS_REGION
echo "Stack creation completed. Final stack status:"
aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus"
