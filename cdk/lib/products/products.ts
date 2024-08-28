import * as cdk from 'aws-cdk-lib';
import { Construct } from "constructs";
import * as servicecatalog from "aws-cdk-lib/aws-servicecatalog";
import * as s3 from "aws-cdk-lib/aws-s3"

type ProductProps = {
    productName: string;
    productOwner: string;
    productVersion: string;
    productStack: servicecatalog.ProductStack
};


export class Product extends Construct {

    // public portfolio: servicecatalog.Portfolio;
    public product: servicecatalog.CloudFormationProduct;
    public assetBucket: s3.Bucket

    /**
     * @param {Construct} scope
     * @param {string} id
     * @param {CustomAPIProps} props
     */
    constructor(scope: Construct, id: string, props: ProductProps) {
        super(scope, id);

        const {
            productName,
            productOwner,
            productVersion,
            productStack
        } = props;

        this.assetBucket = new s3.Bucket(this, 'ProductAssetBucket', {
            bucketName: 'product-stack-asset-bucket-1212313212312',
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            autoDeleteObjects: true,
          });

        this.product = new servicecatalog.CloudFormationProduct(this, "Product", {
            productName: productName,
            owner: productOwner,
            productVersions: [
                {
                    productVersionName: productVersion,
                    cloudFormationTemplate:
                        servicecatalog.CloudFormationTemplate.fromProductStack(productStack)
                },
            ],
        });
    }
}