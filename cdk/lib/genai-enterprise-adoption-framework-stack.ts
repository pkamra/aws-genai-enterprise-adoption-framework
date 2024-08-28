import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Portfolio } from './portfolio/portfolio';
import * as s3 from 'aws-cdk-lib/aws-s3'
import { bedrock } from '@cdklabs/generative-ai-cdk-constructs';
import { GenAIProductStack } from './products/GenAIProductStack/GenAIProductStack';
import { Product } from './products/products';
import { S3BucketProduct } from './products/BucketProductStack/bucket-product-stack';
import * as servicecatalog from "aws-cdk-lib/aws-servicecatalog";


export class GenaiEnterpriseAdoptionFrameworkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);


    const genaiProductAssetBucket = new s3.Bucket(this, 'GenaiProductAssetBucket', {
      bucketName: 'genai-product-stack-asset-bucket-1212313212312',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });


    const testProduct = new servicecatalog.CloudFormationProduct(this, "TestProduct", {
      productName: 'TestProduct',
      owner: 'CCOE',
      productVersions: [
        {
          productVersionName: '1.0',
          validateTemplate: false,
          cloudFormationTemplate: servicecatalog.CloudFormationTemplate.fromProductStack(new S3BucketProduct(this, 'S3BucketProduct'))
        },
      ],
    });

    const genaiProduct = new servicecatalog.CloudFormationProduct(this, "GenAIProduct", {
      productName: 'GenAIProduct',
      owner: 'CCOE',
      productVersions: [
        {
          productVersionName: '1.0',
          validateTemplate: false,
          cloudFormationTemplate: servicecatalog.CloudFormationTemplate.fromProductStack(new GenAIProductStack(this, 'GenAIProduct', {
            assetBucket: genaiProductAssetBucket,
          })),
        },
      ],
    });

    // create a porfolio
    const testPortfolio = new Portfolio(this, 'TestPortfolio', {
      launchRoleName: 'TestPortfolioProductLaunchRole',
      displayName: 'TestPortfolio',
      providerName: 'CCOE',
      description: 'This portfolio manages the set of products specific to GenAI use-cases',
      productsInPortfolio: [testProduct],
    });
  }
}
