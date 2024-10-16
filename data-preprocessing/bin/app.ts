#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { RawDataEtlStack } from '../lib/raw_data_etl_stack';

const app = new cdk.App();

new RawDataEtlStack(app, 'RawDataEtlStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});