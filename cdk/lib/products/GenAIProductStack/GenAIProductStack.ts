import { Construct } from "constructs";
import * as servicecatalog from "aws-cdk-lib/aws-servicecatalog";
import * as cdk from "aws-cdk-lib";
import { bedrock } from '@cdklabs/generative-ai-cdk-constructs';
import { RemovalPolicy } from "aws-cdk-lib";
import * as s3 from 'aws-cdk-lib/aws-s3';
import { ProductStackProps } from "aws-cdk-lib/aws-servicecatalog";

export class GenAIProductStack extends servicecatalog.ProductStack {
    public bucket: s3.Bucket;
    public dataSource: bedrock.S3DataSource;
    public knowledgeBase: bedrock.KnowledgeBase;

    // constructor(scope: Construct, id: string) {
    //     super(scope, id);
    constructor(scope: Construct, id: string, props?: ProductStackProps) {
        super(scope, id);

        // create the bedrock knowledge base
        this.knowledgeBase = new bedrock.KnowledgeBase(this, 'BedrockKnowledgeBase', {
            embeddingsModel: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V1,
            instruction: `Use this knowledge base to answer questions about wealthtech faqs`,
        });

        this.bucket = new s3.Bucket(this, "WealthTechFAQBucket", {
            publicReadAccess: false,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            accessControl: s3.BucketAccessControl.PRIVATE,
            objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            encryption: s3.BucketEncryption.S3_MANAGED,
            removalPolicy: RemovalPolicy.DESTROY,
        });

        // // // ensure that the data is uploaded as part of the cdk deploy
        // new s3deploy.BucketDeployment(this, 'ClientBucketDeployment', {
        //     sources: [s3deploy.Source.asset("knowledge_articles")],
        //     destinationBucket: this.bucket,
        // });

        // set the data source of the s3 bucket for the knowledge base
        this.dataSource = new bedrock.S3DataSource(this, 'DataSource', {
            bucket: this.bucket,
            knowledgeBase: this.knowledgeBase,
            dataSourceName: 'WealthTechDataSource',
            chunkingStrategy: bedrock.ChunkingStrategy.DEFAULT,
            maxTokens: 500,
            overlapPercentage: 20,
        });

    }
}