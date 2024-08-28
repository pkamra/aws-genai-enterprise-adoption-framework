import * as cdk from 'aws-cdk-lib';
import { Construct } from "constructs";
import * as servicecatalog from "aws-cdk-lib/aws-servicecatalog";
import * as iam from "aws-cdk-lib/aws-iam";

type PortfolioProps = {
    launchRoleName: string;
    displayName: string;
    providerName: string;
    description: string;
    productsInPortfolio: servicecatalog.CloudFormationProduct[]
};


export class Portfolio extends Construct {

    private addProductsToPortfolio(productsInPortfolio: servicecatalog.CloudFormationProduct[], serviceCatalogLaunchRole: iam.Role) {
        productsInPortfolio.forEach(product => {
            this.portfolio.addProduct(product);
            this.portfolio.setLaunchRole(product, serviceCatalogLaunchRole)
        });
    }

    public portfolio: servicecatalog.Portfolio;

    /**
     * @param {Construct} scope
     * @param {string} id
     * @param {CustomAPIProps} props
     */
    constructor(scope: Construct, id: string, props: PortfolioProps) {
        super(scope, id);

        const {
            launchRoleName,
            displayName,
            providerName,
            description,
            productsInPortfolio

        } = props;

        const serviceCatalogLaunchRole = new iam.Role(this, "ServiceCatalogLaunchRole", {
            roleName: launchRoleName,
            assumedBy: new iam.ServicePrincipal("servicecatalog.amazonaws.com"),
        });

        this.portfolio = new servicecatalog.Portfolio(this, "Portfolio", {
            displayName: displayName,
            providerName: providerName,
            description: description,
        });

        this.addProductsToPortfolio(productsInPortfolio, serviceCatalogLaunchRole)


    }
}