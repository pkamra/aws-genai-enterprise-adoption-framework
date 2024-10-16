import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import * as path from 'path';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as eventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sns_subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as pipelines from 'aws-cdk-lib/pipelines';


export class RawDataEtlStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const rawDataBucket = new s3.Bucket(this, 'RawDataBucket',{
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const outputBucket = new s3.Bucket(this, 'OutputBucket',{
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const interimOutputPDFBucket = new s3.Bucket(this, 'InterimOutputPDFBucket',{
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    }); // New bucket for PPT to PDF conversion for storing intermediate pdf
    
    
    const intermediateFramesBucket = new s3.Bucket(this, 'IntermediateFramesBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    }); //New bucket that will hold frame by frame the video
    
    const intermediateAudioBucket = new s3.Bucket(this, 'IntermediateAudioBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    }); // New bucket that will hold the audio of the video

   // Adding test data for this stack
    const testDataBucket = new s3.Bucket(this, 'TestDataBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Define the IAM Role for Lambda functions
    const videoprocessinglambdaRole = new iam.Role(this, 'VideoprocessinglambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
    });
    videoprocessinglambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess'));
    
    
    // Define the IAM Role for Lambda functions
    const transcribeCompletionlambdaRole = new iam.Role(this, 'TranscribeCompletionlambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
    });
    transcribeCompletionlambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess'));


    
    const videoProcessingLayer = new lambda.LayerVersion(this, 'VideoProcessingLayer', {
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/videoprocessing-layer'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_9.bundlingImage,
          command: [
            'bash', '-c', [
              'pip install -r requirements.txt -t /asset-output/python',
              'cp -au . /asset-output/python'
            ].join(' && '),
          ],
        },
      }),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
      description: 'A layer to include PDF processor dependencies',
    });
    
    // Lambda function for frame analysis and audio extraction
    const videoProcessingLambda = new lambda.Function(this, 'VideoProcessingLambda', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'audiovideo_processing.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/audiovideo_processor')),
      role: videoprocessinglambdaRole,
      memorySize: 10240,  // 10 GB of memory
      timeout: cdk.Duration.minutes(15),
      ephemeralStorageSize: cdk.Size.gibibytes(10),
      layers: [
        videoProcessingLayer
      ],
      environment: {
        'FRAMES_BUCKET': intermediateFramesBucket.bucketName,
        'AUDIO_BUCKET' : intermediateAudioBucket.bucketName
      },
    });
    

    // Lambda for handling transcription completion
    const transcriptionCompletionLambda = new lambda.Function(this, 'TranscriptionCompletionLambda', {
      runtime: lambda.Runtime.PYTHON_3_10,
      handler: 'transcription_completion.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/transcription_completion')),
      role: transcribeCompletionlambdaRole,
      memorySize: 10240,
      timeout: cdk.Duration.minutes(15),
      ephemeralStorageSize: cdk.Size.gibibytes(10),
      environment: {
        'FRAMES_BUCKET': intermediateFramesBucket.bucketName,
        'OUTPUT_BUCKET': outputBucket.bucketName,
      },
    });
    
    
    //---------------------------PROCESSING OF DOCX/PPT/EXCEL/PDF files------
    const pdfprocessinglambdaRole = new iam.Role(this, 'PdfProcessingLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'), // Lambda Service Principal
    });

    // Attach AdministratorAccess policy to the Lambda role
    pdfprocessinglambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess'));
    
    
    // Define the Lambda execution role with AdministratorAccess
    const interimLambdaRole = new iam.Role(this, 'InterimLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'), // Lambda Service Principal
    });

    // Attach AdministratorAccess policy to the Lambda role
    interimLambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess'));


    const pdfprocessingLayer = new lambda.LayerVersion(this, 'PdfProcessingLayer', {
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/pdfprocessing-layer'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_10.bundlingImage,
          command: [
            'bash', '-c', [
              'pip install -r requirements.txt -t /asset-output/python',
              'cp -au . /asset-output/python'
            ].join(' && '),
          ],
        },
      }),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_10],
      description: 'A layer to include PDF processor dependencies like pymupdf and pillow',
    });
    

    // Create an SQS queue
    const queueToAnalyzeRemainingPDFPages = new sqs.Queue(this, 'QueueToAnalyzeRemaininingPDFPages', {
      visibilityTimeout: cdk.Duration.minutes(15),  // Set visibility timeout to 15 minutes
      retentionPeriod: cdk.Duration.days(4),        // Retention period remains 4 days
      deliveryDelay: cdk.Duration.minutes(1),       // Set delivery delay to 1 minute
    });
    
    const pdfProcessorLambda = new lambda.Function(this, 'PDFProcessor', {
      runtime: lambda.Runtime.PYTHON_3_10,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/pdf_processor')),
      role: pdfprocessinglambdaRole,
      layers: [pdfprocessingLayer],
      timeout: cdk.Duration.minutes(15),
      memorySize: 1024,
      environment: {
        'REGION': this.region,
        'OUTPUT_BUCKET': outputBucket.bucketName,
        'SQS_QUEUE_URL': queueToAnalyzeRemainingPDFPages.queueUrl, 
      },
    });
    

    
    // Add SQS as event source for Lambda
    pdfProcessorLambda.addEventSource(new eventSources.SqsEventSource(queueToAnalyzeRemainingPDFPages, {
      batchSize: 1, 
    }));
    
    // // Grant the Lambda function permissions to interact with the SQS queue (send/receive messages)
    // queueToAnalyzeRemainingPDFPages.grantSendMessages(pdfProcessorLambda);
    // queueToAnalyzeRemainingPDFPages.grantConsumeMessages(pdfProcessorLambda);

    const lambdaImageAsset = new ecr_assets.DockerImageAsset(this, 'LambdaImage', {
      directory: path.join(__dirname, '../lambda/ppt_processor'),
      file: 'lambda.dockerfile',
    });

    console.log(`Docker Image Repository: ${lambdaImageAsset.repository.repositoryUri}`);
    console.log(`Docker Image Tag: ${lambdaImageAsset.imageTag}`);

    const interimProcessorLambda = new lambda.DockerImageFunction(this, 'PPTDOCXLSProcessor', {
      code: lambda.DockerImageCode.fromEcr(lambdaImageAsset.repository, {
        tagOrDigest: lambdaImageAsset.imageTag,
      }),
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      role: interimLambdaRole,
      environment: {
        'REGION': this.region,
        'OUTPUT_BUCKET': interimOutputPDFBucket.bucketName, // Set the output bucket for PPT. DOCX, DOC,XLS,XLSX  to PDF conversion
      },
    });

    rawDataBucket.grantRead(pdfProcessorLambda); //This will convert the complex pdf to text format
    outputBucket.grantWrite(pdfProcessorLambda); //Output is pdf files
    interimOutputPDFBucket.grantWrite(interimProcessorLambda); // Grant write permission for interimProcessorLambda for ppt/docx/excel files
    rawDataBucket.grantRead(interimProcessorLambda); //lambda that converst from ppt/doc/excel to pdf
    
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(pdfProcessorLambda), { suffix: '.pdf' }); //Complex PDF processing lambda
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.ppt' });
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.pptx' });
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.docx' });
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.xlsx' });
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.xls' });
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.excel' });
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(interimProcessorLambda), { suffix: '.html' });
    interimOutputPDFBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(pdfProcessorLambda), { suffix: '.pdf' }); // Trigger summarizer on PDF creation
    
    // Trigger video processing Lambda when MP4 files are uploaded to the raw data bucket
    rawDataBucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(videoProcessingLambda), {
      suffix: '.mp4',
    });
    rawDataBucket.grantRead(videoProcessingLambda);// to trigger the videoprocessinglambda
    intermediateFramesBucket.grantWrite(videoProcessingLambda); //videoprocesinglambda will write frames
    intermediateAudioBucket.grantWrite(videoProcessingLambda); //videoprocesinglambda will write the trsnscript through transcribe job
    
    // Add S3 event notification to trigger the Lambda function when a new object is created
    intermediateAudioBucket.addEventNotification(s3.EventType.OBJECT_CREATED_PUT, new s3n.LambdaDestination(transcriptionCompletionLambda), {
      suffix: '.json',  // Trigger on JSON files (i.e., transcription result files)
    });
    intermediateFramesBucket.grantRead(transcriptionCompletionLambda);//transcriptionLambda will read frame data to collate with transcribed text 
    intermediateAudioBucket.grantRead(transcriptionCompletionLambda);//tarnscriptionLambda will read the tarnscript from this bucket.
    outputBucket.grantWrite(transcriptionCompletionLambda);
 
    // Output test data URL for easier access
    new cdk.CfnOutput(this, 'TestDataBucketURL', {
      value: testDataBucket.bucketWebsiteUrl,
      description: 'The URL to access the test data bucket.',
      exportName: 'TestDataBucketURL',
    });

    // Outputs for various resources in the stack
    new cdk.CfnOutput(this, 'RawDataBucketName', {
      value: rawDataBucket.bucketName,
      description: 'Name of the raw data S3 bucket',
      exportName: 'RawDataBucketName',
    });

    new cdk.CfnOutput(this, 'OutputBucketName', {
      value: outputBucket.bucketName,
      description: 'Name of the output S3 bucket',
      exportName: 'OutputBucketName',
    });

    new cdk.CfnOutput(this, 'VideoProcessingLambdaArn', {
      value: videoProcessingLambda.functionArn,
      description: 'ARN of the Video Processing Lambda',
      exportName: 'VideoProcessingLambdaArn',
    });

    new cdk.CfnOutput(this, 'TranscriptionCompletionLambdaArn', {
      value: transcriptionCompletionLambda.functionArn,
      description: 'ARN of the Transcription Completion Lambda',
      exportName: 'TranscriptionCompletionLambdaArn',
    });
    
    // Output for PDF Processor Lambda
    new cdk.CfnOutput(this, 'PDFProcessorLambdaArn', {
      value: pdfProcessorLambda.functionArn,
      description: 'ARN of the PDF Processor Lambda which will take complex PDF documents and use LLM to convert to structured text ',
      exportName: 'PDFProcessorLambdaArn',
    });
    
    // Output for PPT/Word/Excel to PDF Conversion Lambda
    new cdk.CfnOutput(this, 'PPTDOCXLSProcessorLambdaArn', {
      value: interimProcessorLambda.functionArn,
      description: 'ARN of the PPT/Word/Excel Processor Lambda which will convert the data to an intermediate PDF format',
      exportName: 'PPTDOCXLSProcessorLambdaArn',
    });
    
    // Output for SQS Queue
    new cdk.CfnOutput(this, 'QueueToAnalyzeRemainingPDFPagesUrl', {
      value: queueToAnalyzeRemainingPDFPages.queueUrl,
      description: 'URL of the SQS queue used for processing remaining PDF pages for a specific document',
      exportName: 'QueueToAnalyzeRemainingPDFPagesUrl',
    });
    
  }
}
