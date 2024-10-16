import boto3
import json
import logging
import os

s3_client = boto3.client('s3')
transcribe = boto3.client('transcribe')
bedrock_runtime = boto3.client('bedrock-runtime')
frames_bucket = os.environ['FRAMES_BUCKET']
output_bucket = os.environ['OUTPUT_BUCKET']

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def generate_bedrock_insights(video_labels, transcript_text):
    """
    Generates insights using Amazon Bedrock based on video labels and transcript.
    """
    prompt = f"""
    Video Analysis: The following labels were detected in the frames: {json.dumps(video_labels)}.
    Transcript of the video: {transcript_text}.
    Can you summarize the events described in both the video and audio, and provide insights based on both?
    """
    
    response = bedrock_runtime.invoke_model(
        modelId='anthropic.claude-3-sonnet-20240229-v1:0',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31", 
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }),
        contentType='application/json',
        accept='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    return response_body['content'][0]['text']

def handler(event, context):
    """
    Lambda handler function that processes transcription and video labels, generates insights, and stores results.
    """
    try:
        print(f"Event received: {json.dumps(event, indent=2)}")
        
        aws_request_id = context.aws_request_id  # Unique request ID for this Lambda execution

        # Get the S3 object details from the event
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        object_key = event['Records'][0]['s3']['object']['key']

        # Download transcription result from S3
        transcription_result = s3_client.get_object(Bucket=bucket_name, Key=object_key)['Body'].read().decode('utf-8')
        transcription_data = json.loads(transcription_result)
        transcript_text = transcription_data['results']['transcripts'][0]['transcript']

        # Retrieve video frame labels from S3
        video_labels_key = object_key.replace('transcription', 'labels')
        video_labels = s3_client.get_object(Bucket=frames_bucket, Key=video_labels_key)['Body'].read().decode('utf-8')
        video_labels_data = json.loads(video_labels)

        # Perform Bedrock insights analysis
        bedrock_insights = generate_bedrock_insights(video_labels_data, transcript_text)
        
        # # Save combined results to S3 with a unique output key based on the request ID
        # combined_results = {
        #     'transcription': transcript_text,
        #     'video_labels': video_labels_data,
        #     'bedrock_insights': bedrock_insights,
        # }
        
        # output_key = object_key.replace('_transcription.json', f'_combined_results_{aws_request_id}.json')
        # s3_client.put_object(Bucket=output_bucket, Key=output_key, Body=json.dumps(combined_results))

        # print(f"Combined results saved to s3://{output_bucket}/{output_key}")
        
        # Create a text version of the combined results
        combined_text = f"Transcript:\n{transcript_text}\n\n"
        combined_text += f"Video Labels:\n{json.dumps(video_labels_data, indent=4)}\n\n"
        combined_text += f"Bedrock Insights:\n{bedrock_insights}\n"
        
        # Save the combined text to S3 
        output_key = object_key.replace('_transcription', '_combined_results')
        output_key = object_key.replace('.json', '.txt')
        s3_client.put_object(Bucket=output_bucket, Key=output_key, Body=combined_text)

        print(f"Combined results saved as text to s3://{output_bucket}/{output_key}")


        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Transcription processing and Bedrock analysis completed.',
                'combined_results_s3_key': output_key,
            })
        }

    except Exception as e:
        logger.error(f"Error processing transcription result: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Failed to process transcription result and perform Bedrock analysis.',
                'error': str(e),
            })
        }
