#!/bin/bash

# If not already cloned, clone the remote repository (https://github.com/aws-samples/amazon-bedrock-samples) and change working directory to insurance agent shell folder
# cd amazon-bedrock-samples/agents/insurance-claim-lifecycle-automation/shell/

# Ensure script is executable
# chmod u+x create-customer-resources.sh

# Define environment variables
# export STACK_NAME=<YOUR-STACK-NAME> # Stack name must be lower case for S3 bucket naming convention
# export SNS_EMAIL=<YOUR-POLICY-HOLDER-EMAIL> # Email used for SNS notifications
# export EVIDENCE_UPLOAD_URL=<YOUR-EVIDENCE-UPLOAD-URL> # URL provided by the agent to the policy holder for evidence upload
# export AWS_REGION=<YOUR-STACK-REGION> # Stack deployment region

# Source the script to set up resources
# source ./create-customer-resources.sh

# Create Lambda layers
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ARTIFACT_BUCKET_NAME=$STACK_NAME-customer-resources
export DATA_LOADER_KEY="agent/lambda/data-loader/loader_deployment_package.zip"
export CREATE_CLAIM_KEY="agent/lambda/action-groups/create_claim.zip"
export GATHER_EVIDENCE_KEY="agent/lambda/action-groups/gather_evidence.zip"
export SEND_REMINDER_KEY="agent/lambda/action-groups/send_reminder.zip"

# Create artifact bucket
aws s3 mb s3://${ARTIFACT_BUCKET_NAME} --region ${AWS_REGION}

# Copy Lambda artifacts to artifact bucket
aws s3 cp ../agent/ s3://${ARTIFACT_BUCKET_NAME}/agent/ --region ${AWS_REGION} --recursive --exclude ".DS_Store"

# Publish Lambda layers
export BEDROCK_AGENTS_LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name bedrock-agents \
    --description "Agents for Bedrock Layer" \
    --license-info "MIT" \
    --content S3Bucket=${ARTIFACT_BUCKET_NAME},S3Key=agent/lambda/lambda-layer/bedrock-agents-layer.zip \
    --compatible-runtimes python3.11 \
    --region ${AWS_REGION} \
    --query LayerVersionArn --output text)

export CFNRESPONSE_LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name cfnresponse \
    --description "cfnresponse Layer" \
    --license-info "MIT" \
    --content S3Bucket=${ARTIFACT_BUCKET_NAME},S3Key=agent/lambda/lambda-layer/cfnresponse-layer.zip \
    --compatible-runtimes python3.11 \
    --region ${AWS_REGION} \
    --query LayerVersionArn --output text)

# Deploy CloudFormation stack
aws cloudformation create-stack \
--stack-name ${STACK_NAME} \
--template-body file://../cfn/bedrock-customer-resources.yml \
--parameters \
ParameterKey=ArtifactBucket,ParameterValue=${ARTIFACT_BUCKET_NAME} \
ParameterKey=DataLoaderKey,ParameterValue=${DATA_LOADER_KEY} \
ParameterKey=CreateClaimKey,ParameterValue=${CREATE_CLAIM_KEY} \
ParameterKey=GatherEvidenceKey,ParameterValue=${GATHER_EVIDENCE_KEY} \
ParameterKey=SendReminderKey,ParameterValue=${SEND_REMINDER_KEY} \
ParameterKey=BedrockAgentsLayerArn,ParameterValue=${BEDROCK_AGENTS_LAYER_ARN} \
ParameterKey=CfnresponseLayerArn,ParameterValue=${CFNRESPONSE_LAYER_ARN} \
ParameterKey=SNSEmail,ParameterValue=${SNS_EMAIL} \
ParameterKey=EvidenceUploadUrl,ParameterValue=${EVIDENCE_UPLOAD_URL} \
ParameterKey=S3DataSource,ParameterValue=<YOUR-S3-BUCKET> \
ParameterKey=AgentName,ParameterValue=<YOUR-AGENT-NAME> \
ParameterKey=AgentInstructions,ParameterValue="<YOUR-AGENT-INSTRUCTIONS>" \
ParameterKey=FoundationModel,ParameterValue=<YOUR-FOUNDATION-MODEL> \
ParameterKey=KnowledgeBaseName,ParameterValue=<YOUR-KNOWLEDGE-BASE-NAME> \
ParameterKey=EmbeddingModel,ParameterValue=<YOUR-EMBEDDING-MODEL> \
ParameterKey=VectorStoreType,ParameterValue=<YOUR-VECTOR-STORE-TYPE> \
ParameterKey=ChunkingStrategy,ParameterValue=<YOUR-CHUNKING-STRATEGY> \
ParameterKey=ChunkingMaxTokens,ParameterValue=<YOUR-CHUNKING-MAX-TOKENS> \
ParameterKey=ChunkingOverlapPercentage,ParameterValue=<YOUR-CHUNKING-OVERLAP-PERCENTAGE> \
ParameterKey=PromptTemplateLocation,ParameterValue=<YOUR-PROMPT-TEMPLATE-LOCATION> \
ParameterKey=LLMAppExposure,ParameterValue=<YOUR-LLM-APP-EXPOSURE> \
ParameterKey=BedrockCustomResourceKey,ParameterValue=<YOUR-BEDROCK-CUSTOM-RESOURCE-KEY> \
--capabilities CAPABILITY_NAMED_IAM \
--region ${AWS_REGION}

# Wait for stack creation to complete
echo "Waiting for stack creation to complete..."
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region ${AWS_REGION}
echo "Stack creation completed."

# Describe stack status
echo "Stack status:"
aws cloudformation describe-stacks --stack-name $STACK_NAME --region ${AWS_REGION} --query "Stacks[0].StackStatus"
