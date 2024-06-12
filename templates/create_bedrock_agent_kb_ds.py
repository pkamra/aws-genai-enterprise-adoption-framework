import os
import json
import time
import uuid
import boto3
import logging
import botocore
import cfnresponse
from requests_aws4auth import AWS4Auth
from opensearchpy import OpenSearch, RequestsHttpConnection

# Initialize clients
s3_client = boto3.client('s3')
iam_client = boto3.client('iam')
lambda_client = boto3.client('lambda')
bedrock_agent_client = boto3.client("bedrock-agent")
opensearch_serverless_client = boto3.client('opensearchserverless')

# Env variables
agent_name = os.environ["AGENT_NAME"]
kb_name = os.environ["KB_NAME"]
s3_bucket_name = os.environ["S3_DATA_SOURCE"]
vector_store_type = os.environ["VECTOR_STORE_TYPE"]
region = os.environ["AWS_REGION"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

 # Generates a random 4-character suffix for unique resource naming
def generate_unique_resource_prefix():
    return uuid.uuid4().hex[:4] 

# Creates an OpenSearch Serverless collection encryption policy.
def create_encryption_policy(kb_unique_name):

    try:
        response = opensearch_serverless_client.create_security_policy(
            description=f'Encryption policy for knowledge base collection: {kb_unique_name}.',
            name=f'{kb_unique_name}-kb-encryption',
            policy=json.dumps({
                "Rules": [
                    {
                        "ResourceType": "collection",
                        "Resource": [
                            f"collection/{kb_unique_name}-collection*"
                        ]
                    }
                ],
                "AWSOwnedKey": True
            }),
            type='encryption'
        )
        logger.info(f'Encryption policy created: {response}')
    
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            logger.info('[ConflictException] The policy name or rules conflict with an existing policy.')
        else:
            raise error

# Creates an OpenSearch Serverless collection network policy.
def create_network_policy(kb_unique_name):

    try:
        response = opensearch_serverless_client.create_security_policy(
            description=f'Network policy for knowledge base collection: {kb_unique_name}.',
            name=f'{kb_unique_name}-kb-network',
            policy=json.dumps([
                {
                    "Description": f"Public access for the knowledge base collection: {kb_unique_name}.",
                    "Rules": [
                        {
                            "ResourceType": "dashboard",
                            "Resource": [f"collection/{kb_unique_name}-collection*"]
                        },
                        {
                            "ResourceType": "collection",
                            "Resource": [f"collection/{kb_unique_name}-collection*"]
                        }
                    ],
                    "AllowFromPublic": True
                }
            ]),
            type='network'
        )
        logger.info(f'Network policy created: {response}')
    
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            logger.info('[ConflictException] A network policy with this name already exists.')
        else:
            raise error

# Creates an OpenSearch Serverless collection access policy.
def create_access_policy(kb_unique_name, bedrock_lambda_role_arn, account_role_arn):

    try:
        response = opensearch_serverless_client.create_access_policy(
            description=f'Data access policy for knowledge base collection: {kb_unique_name}.',
            name=f'{kb_unique_name}-kb-access',
            policy=json.dumps([
                {
                    "Rules": [
                        {
                            "Resource": [f"index/{kb_unique_name}-collection*/*"],
                            "Permission": [
                                "aoss:CreateIndex",
                                "aoss:DeleteIndex",
                                "aoss:UpdateIndex",
                                "aoss:DescribeIndex",
                                "aoss:ReadDocument",
                                "aoss:WriteDocument"
                            ],
                            "ResourceType": "index"
                        },
                        {
                            "Resource": [f"collection/{kb_unique_name}-collection*"],
                            "Permission": [
                                "aoss:CreateCollectionItems",
                                "aoss:DescribeCollectionItems",
                                "aoss:DeleteCollectionItems",
                                "aoss:UpdateCollectionItems"
                            ],
                            "ResourceType": "collection"
                        }
                    ],
                    "Principal": [bedrock_lambda_role_arn, account_role_arn]
                }
            ]),
            type='data'
        )
        logger.info(f'Access policy created: {response}')
    
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            logger.info('[ConflictException] An access policy with this name already exists.')
        else:
            raise error

# Creates OpenSearch Serverless collection for knowledge base
def create_opensearch_collection(kb_unique_name):

    try:
        response = opensearch_serverless_client.create_collection(
            name=f'{kb_unique_name}-collection',
            description=f'Collection for knowledge base: {kb_unique_name}.',
            type='VECTORSEARCH'
        )
        logger.info(f'Collection created: {response}')
        return response['createCollectionDetail']['arn']
    
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'ConflictException':
            logger.info('[ConflictException] A collection with this name already exists. Try another name.')
        else:
            raise error

# Creates an OpenSearch Serverless vector index
def index_data(host, awsauth, embedding_model, vector_index_name, metadata_field, text_field, vector_field_name,):
    
    # Determine dimension based on 'embedding_model'
    model_dimensions = {
        'amazon.titan-embed-text-v1': 1536,
        'cohere.embed-english-v3': 1024,
        'cohere.embed-multilingual-v3': 1024,
        # Add other models with their dimensions here as needed
    }

    if embedding_model not in model_dimensions:
        raise ValueError(f"Unsupported embedding model: {embedding_model}. Supported models are: {list(model_dimensions.keys())}")

    dimension = model_dimensions[embedding_model]

    opensearch_client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )
    time.sleep(45)
    body = {
      "mappings": {
        "properties": {
          f"{metadata_field}": {
            "type": "keyword",
            "index": False
          },
          "id": {
            "type": "keyword",
            "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
              }
            }
          },
          f"{text_field}": {
            "type": "text",
            "index": True
          },
          f"{vector_field_name}": {
            "type": "knn_vector",
            "dimension": dimension,
            "method": {
              "engine": "faiss",
              "space_type": "l2",
              "name": "hnsw",
              "parameters": {
                "ef_construction": 512,
                "m": 16
              }
            }
          }
        }
      },
      "settings": {
        "index": {
          "number_of_shards": 2,
          "knn.algo_param": {
            "ef_search": 512
          },
          "knn": True,
        }
      }
    }

    try:
        response = opensearch_client.indices.create(index=vector_index_name, body=body)
        logger.info(f'Index created: {response}')
    except Exception as e:
        logger.error(f'Error creating index: {e}')
        raise

# Syncs Bedrock knowledge base using an ingestion job
def update_knowledge_base(selected_ds_id, selected_kb_id):

    description = "Programmatic update of Bedrock Knowledge Base Data Source"
    try:
        response = agent_client.start_ingestion_job(
            dataSourceId=selected_ds_id,
            description=description,
            knowledgeBaseId=selected_kb_id
        )
    except Exception as e:
        st.error(f"Error starting ingestion job: {e}")
    finally:
        file_obj.close()

# Waits for OpenSearch Serverless collection 'active' state
def wait_for_collection_creation(kb_unique_name, awsauth, embedding_model, vector_index_name, vector_field_name, text_field, metadata_field):

    response = opensearch_serverless_client.batch_get_collection(names=[f'{kb_unique_name}-collection'])
    
    while response['collectionDetails'][0]['status'] == 'CREATING':
        logger.info('Creating collection...')
        time.sleep(30)
        response = opensearch_serverless_client.batch_get_collection(names=[f'{kb_unique_name}-collection'])
    
    logger.info(f'Collection successfully created: {response["collectionDetails"]}')
    
    host = response['collectionDetails'][0]['collectionEndpoint']
    final_host = host.replace("https://", "")

    # update_knowledge_base(file_content, bucket_name, s3_file_name, selected_ds_id, selected_kb_id):
    index_data(final_host, awsauth, embedding_model, vector_index_name, metadata_field, text_field, vector_field_name)

# Creates Bedrock knowledge base with different storage configurations based on the 'VECTOR_STORE_TYPE' environment variable
def create_knowledge_base(kb_unique_name, account_id, bedrock_lambda_role_arn, embedding_model, vector_index_name, vector_field_name, text_field, metadata_field, collection_arn=None,):

    if vector_store_type == 'OPENSEARCH_SERVERLESS':
        storage_configuration = {
            'type': 'OPENSEARCH_SERVERLESS',
            'opensearchServerlessConfiguration': {
                'collectionArn': collection_arn,
                'vectorIndexName': vector_index_name,
                'fieldMapping': {
                    'vectorField': vector_field_name,
                    'textField': text_field,
                    'metadataField': metadata_field
                }
            }
        }
    elif vector_store_type == 'PINECONE':
        storage_configuration = {
            'type': 'PINECONE',
            'pineconeConfiguration': {
                'connectionString': 'https://xxxx.pinecone.io',  # Replace with actual connection string
                'credentialsSecretArn': 'arn:aws:secretsmanager:us-west-2:123456789012:secret:pinecone-secret-abc123',  # Replace with actual ARN
                'namespace': 'kb-namespace',
                'fieldMapping': {
                    'textField': text_field,
                    'metadataField': metadata_field
                }
            }
        }
    elif vector_store_type == 'REDIS_ENTERPRISE_CLOUD':
        storage_configuration = {
            'type': 'REDIS_ENTERPRISE_CLOUD',
            'redisEnterpriseCloudConfiguration': {
                'credentialsSecretArn': 'arn:aws:secretsmanager:us-west-2:123456789012:secret:redis-secret-abc123',  # Replace with actual ARN
                'endpoint': 'https://xxxx.redis-enterprise.io',  # Replace with actual endpoint
                'vectorIndexName': 'bedrock-knowledge-base-default-index',
                'fieldMapping': {
                    'vectorField': 'bedrock-knowledge-base-default-vector',
                    'textField': text_field,
                    'metadataField': metadata_field
                }
            }
        }
    elif vector_store_type == 'MONGO_DB_ATLAS':
        storage_configuration = {
            'type': 'MONGO_DB_ATLAS',
            'mongoDbAtlasConfiguration': {
                'collectionName': 'knowledgeBaseCollection',
                'credentialsSecretArn': 'arn:aws:secretsmanager:us-west-2:123456789012:secret:mongo-secret-abc123',  # Replace with actual ARN
                'databaseName': 'knowledgeBaseDatabase',
                'endpoint': 'https://xxxx.mongodb.net',  # Replace with actual endpoint
                'vectorIndexName': 'bedrock-knowledge-base-default-index',
                'fieldMapping': {
                    'vectorField': 'bedrock-knowledge-base-default-vector',
                    'textField': text_field,
                    'metadataField': metadata_field
                }
            }
        }
    else:
        storage_configuration = {
            'type': 'RDS',
            'rdsConfiguration': {
                'resourceArn': f'arn:aws:rds:{region}:{account_id}:cluster:knowledgebase-cluster',  # Replace with actual values
                'credentialsSecretArn': f'arn:aws:secretsmanager:{region}:{account_id}:secret:rds!cluster-4f5961a1-ebd5-4887-818f-0f902e945e04-eFxmC6',  # Replace with actual ARN
                'databaseName': 'postgres',
                'tableName': 'bedrock_integration.bedrock_kb',
                'fieldMapping': {
                    'vectorField': 'vectorKey',
                    'textField': text_field,
                    'metadataField': metadata_field,
                    'primaryKeyField': 'id'
                }
            }
        }

    knowledge_base_response = bedrock_agent_client.create_knowledge_base(
        description=f'Knowledge base: {kb_unique_name}',
        name=f'{kb_unique_name}-knowledge-base',
        knowledgeBaseConfiguration={
            'type': 'VECTOR',
            'vectorKnowledgeBaseConfiguration': {
                'embeddingModelArn': f"arn:aws:bedrock:{region}::foundation-model/{embedding_model}"
            }
        },
        roleArn=bedrock_lambda_role_arn,
        storageConfiguration=storage_configuration
    )

    logger.info(f'Knowledge base created: {knowledge_base_response}')
    return knowledge_base_response['knowledgeBase']['knowledgeBaseId']

# Creates Bedrock knowledge base data source
def create_data_source(kb_unique_name, knowledge_base_id, kms_key_arn, embedding_model, chunking_strategy, chunking_max_tokens, chunking_overlap, bucket_owner_account_id=None, inclusion_prefixes=None):
    
    data_source_configuration = {
        's3Configuration': {
            'bucketArn': f"arn:aws:s3:::{s3_bucket_name}"
        },
        'type': 'S3'
    }

    if bucket_owner_account_id:
        data_source_configuration['s3Configuration']['bucketOwnerAccountId'] = bucket_owner_account_id
    if inclusion_prefixes:
        data_source_configuration['s3Configuration']['inclusionPrefixes'] = inclusion_prefixes

    vector_ingestion_configuration = {
        'chunkingConfiguration': {
            'chunkingStrategy': chunking_strategy
        }
    }
    
    if chunking_strategy == 'FIXED_SIZE':
        if chunking_max_tokens is None or chunking_overlap is None:
            raise ValueError("max_tokens and overlap_percentage must be provided for FIXED_SIZE chunking strategy.")

        # Determine dimension based on 'embedding_model'
        model_tokens = {
            'amazon.titan-embed-text-v1': 8192,
            'cohere.embed-english-v3': 512,
            'cohere.embed-multilingual-v3': 512,
            # Add other models with their dimensions here as needed
        }

        if embedding_model not in model_tokens:
            raise ValueError(f"Unsupported embedding model: {embedding_model}. Supported models are: {list(model_dimensions.keys())}")

        tokens = model_tokens[embedding_model]

        if chunking_max_tokens > tokens:
            chunking_max_tokens = tokens

        vector_ingestion_configuration['chunkingConfiguration']['fixedSizeChunkingConfiguration'] = {
            'maxTokens': chunking_max_tokens,
            'overlapPercentage': chunking_overlap
        }
    
    request_payload = {
        'description': f"Data source for knowledge base: {kb_name}",
        'dataDeletionPolicy': 'DELETE',
        'dataSourceConfiguration': data_source_configuration,
        'knowledgeBaseId': knowledge_base_id,
        'name': f"{kb_unique_name}-data-source",
        'serverSideEncryptionConfiguration': {
            'kmsKeyArn': kms_key_arn
        },
        'vectorIngestionConfiguration': vector_ingestion_configuration
    }

    data_source_response = bedrock_agent_client.create_data_source(**request_payload)
    logger.info(f'Data source created: {data_source_response}')
    return data_source_response['dataSource']['dataSourceId']

# Creates Bedrock agent action groups by iterating through list of dictionaries
def create_action_groups(agent_id, agent_version, properties):

    try:
        # Define action groups
        action_groups = [
            {
                "Name": "create-claim",
                "Description": "Use this action group to create an insurance claim",
                "FunctionArn": properties['CreateClaimFunctionArn'],
                "FunctionSchema": {
                    'functions': [
                        {
                            'name': 'createClaim',
                            'description': 'Function to create an insurance claim',
                            'parameters': {
                                'claimType': {
                                    'description': 'Type of the claim',
                                    'required': True,
                                    'type': 'string'
                                },
                                'policyNumber': {
                                    'description': 'Policy number associated with the claim',
                                    'required': True,
                                    'type': 'string'
                                }
                            }
                        }
                    ]
                }
            },
            {
                "Name": "gather-evidence",
                "Description": "Use this action group to send the user a URL for evidence upload on open status claims with pending documents. Return the documentUploadUrl to the user",
                "FunctionArn": properties['GatherEvidenceFunctionArn'],
                "FunctionSchema": {
                    'functions': [
                        {
                            'name': 'gatherEvidence',
                            'description': 'Function to gather evidence for a claim',
                            'parameters': {
                                'claimId': {
                                    'description': 'ID of the claim',
                                    'required': True,
                                    'type': 'string'
                                }
                            }
                        }
                    ]
                }
            },
            {
                "Name": "send-reminder",
                "Description": "Use this action group to check claim status, identify missing or pending documents, and send reminders to policy holders",
                "FunctionArn": properties['SendReminderFunctionArn'],
                "FunctionSchema": {
                    'functions': [
                        {
                            'name': 'sendReminder',
                            'description': 'Function to send reminders for pending claims',
                            'parameters': {
                                'claimId': {
                                    'description': 'ID of the claim',
                                    'required': True,
                                    'type': 'string'
                                },
                                'reminderType': {
                                    'description': 'Type of reminder to send',
                                    'required': False,
                                    'type': 'string'
                                }
                            }
                        }
                    ]
                }
            },
            {
                "Name": "user-input",
                "Description": "",
                "FunctionArn": None,
                "ParentActionGroupSignature": 'AMAZON.UserInput'
            }
        ]

        # Create action groups
        for action_group in action_groups:
            if action_group["Name"] == "user-input":
                response = bedrock_agent_client.create_agent_action_group(
                    agentId=agent_id,
                    agentVersion=agent_version,
                    actionGroupName=action_group['Name'],
                    parentActionGroupSignature=action_group['ParentActionGroupSignature']
                )
            else:
                response = bedrock_agent_client.create_agent_action_group(
                    agentId=agent_id,
                    agentVersion=agent_version,
                    actionGroupName=action_group['Name'],
                    description=action_group['Description'],
                    actionGroupExecutor={
                        'lambda': action_group['FunctionArn']
                    },
                    functionSchema=action_group['FunctionSchema']
                )
            logger.info(f"Action group created: {response}")

    except Exception as e:
        logger.error(f"Failed to create action groups: {e}")
        raise


# Creates Bedrock agent
def create_agent(agent_unique_name, bedrock_lambda_role_arn, foundation_model, agent_instructions, customer_encryption_key_arn=None):
    try:
        agent_response = bedrock_agent_client.create_agent(
            agentName=f"{agent_unique_name}-agent",
            agentResourceRoleArn=bedrock_lambda_role_arn,
            description=f"Agent: {agent_name}",
            foundationModel=foundation_model,
            instruction=agent_instructions,
            customerEncryptionKeyArn=customer_encryption_key_arn,
            idleSessionTTLInSeconds=300,
        )
        logger.info(f'Agent created HERE: {agent_response}')
        return agent_response['agent']['agentId']

    except Exception as e:
        logger.error(f'Failed to create agent: {e}')
        if 'failureReasons' in e.response:
            logger.error(f'Failure reasons: {e.response["failureReasons"]}')
        if 'recommendedActions' in e.response:
            logger.error(f'Recommended actions: {e.response["recommendedActions"]}')
        raise

# Associates knowledge base with agent
def associate_knowledge_base(agent_id, knowledge_base_id, agent_version='DRAFT'):

    try:
        associate_response = bedrock_agent_client.associate_agent_knowledge_base(
            agentId=agent_id,
            agentVersion=agent_version,
            description=f"Knowledge base for agent ID: {agent_id}",
            knowledgeBaseId=knowledge_base_id,
            knowledgeBaseState='ENABLED'
        )
        logger.info(f'Knowledge base associated: {associate_response}')
    
    except Exception as e:
        logger.error(f'Failed to associate knowledge base: {e}')
        raise


# Main handler
def lambda_handler(event, context):
    request_type = event['RequestType']
    properties = event['ResourceProperties']

    embedding_model = properties['EmbeddingModel']
    foundation_model = properties['FoundationModel']
    agent_instructions = properties['AgentInstructions']

    create_claim_function_arn = properties['CreateClaimFunctionArn']
    gather_evidence_function_arn = properties['GatherEvidenceFunctionArn']
    send_reminder_function_arn = properties['SendReminderFunctionArn']
    
    bedrock_lambda_role_arn = properties['BedrockRoleArn']
    account_role_arn = properties['AccountRoleArn']
    kms_key_arn = properties['KMSKeyArn']

    chunking_strategy = properties['ChunkingStrategy']
    chunking_max_tokens = int(properties['ChunkingMaxTokens'])
    chunking_overlap = int(properties['ChunkingOverlapPercentage'])

    vector_field_name = f"{agent_name}-embeddings"
    vector_index_name = f"{agent_name}-vector"
    text_field = "AMAZON_BEDROCK_TEXT_CHUNK"
    metadata_field = "AMAZON_BEDROCK_METADATA"

    agent_version = "DRAFT"

    unique_resource_prefix = generate_unique_resource_prefix()
    agent_unique_name = f"{agent_name}-{unique_resource_prefix}"
    kb_unique_name = f"{kb_name}-{unique_resource_prefix}"
    print(f"Agent Resource Name: {agent_unique_name}\nKnowledge Base Resource Name: {kb_unique_name}")

    account_id = context.invoked_function_arn.split(":")[4]
    agent_id = None
    
    if request_type == 'Create':
        try:
            # Create OpenSearch Serverless collection and policies
            collection_arn = None

            if vector_store_type == 'OPENSEARCH_SERVERLESS':
                create_encryption_policy(kb_unique_name)
                create_network_policy(kb_unique_name)
                create_access_policy(kb_unique_name, bedrock_lambda_role_arn, account_role_arn)
                collection_arn = create_opensearch_collection(kb_unique_name)

                # Set up auth for Opensearch client
                service = 'aoss'
                credentials = boto3.Session().get_credentials()
                awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)

                # Wait for collection to be created
                wait_for_collection_creation(kb_unique_name, awsauth, embedding_model, vector_index_name, vector_field_name, text_field, metadata_field)
                time.sleep(30)

            # Create Bedrock knowledge base
            knowledge_base_id = create_knowledge_base(kb_unique_name, account_id, bedrock_lambda_role_arn, embedding_model, vector_index_name, vector_field_name, text_field, metadata_field, collection_arn)

            # Create Bedrock data source
            create_data_source(kb_unique_name, knowledge_base_id, kms_key_arn, embedding_model, chunking_strategy, chunking_max_tokens, chunking_overlap)

            # Create Bedrock agent with action groups
            agent_id = create_agent(agent_unique_name, bedrock_lambda_role_arn, foundation_model, agent_instructions, kms_key_arn)
            time.sleep(30)
            create_action_groups(agent_id, agent_version, properties)

            # Associate knowledge base with agent
            associate_knowledge_base(agent_id, knowledge_base_id, agent_version)

            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData={})
        except Exception as e:
            logger.error("Failed to load data into DynamoDB table: %s", str(e))
            cfnresponse.send(event, context, cfnresponse.FAILED, responseData={"Error": str(e)})

    elif request_type == 'Delete':
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData={})

    return {
        'statusCode': 200,
        'body': json.dumps('Function execution completed successfully')
    }
