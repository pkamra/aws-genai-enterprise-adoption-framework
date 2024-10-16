import boto3
import cv2
import os
import json
import logging
import urllib.parse

# Initialize AWS clients
s3_client = boto3.client('s3')
rekognition = boto3.client('rekognition')
transcribe = boto3.client('transcribe')

# Define constants
frames_bucket = os.environ['FRAMES_BUCKET']
audio_bucket = os.environ['AUDIO_BUCKET']

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def analyze_frames(video_file, context):
    """
    Analyzes frames in the video file using Amazon Rekognition.
    This version ensures unique file names for each invocation using aws_request_id.
    
    Args:
    - video_file: Path to the video file.
    - context: Lambda context object to access aws_request_id for unique file naming.
    
    Returns:
    - video_labels: A list of labels detected for each frame.
    """
    print(f"Starting frame analysis for {video_file}")
    video = cv2.VideoCapture(video_file)
    frame_counter = 0
    video_labels = []
    
    while video.isOpened():
        ret, frame = video.read()
        if not ret:
            print(f"End of video reached after {frame_counter} frames.")
            break
        frame_counter += 1

        # Use aws_request_id for unique file names
        frame_filename = f'/tmp/frame_{frame_counter}_{context.aws_request_id}.jpg'
        cv2.imwrite(frame_filename, frame)
        print(f"Frame {frame_counter} saved as {frame_filename}")
        
        # Process the frame using Rekognition
        with open(frame_filename, 'rb') as image:
            rekognition_response = rekognition.detect_labels(
                Image={'Bytes': image.read()}, MaxLabels=10, MinConfidence=70
            )
            labels = [label['Name'] for label in rekognition_response['Labels']]
            video_labels.append({f'Frame {frame_counter}': labels})
            print(f"Rekognition labels for frame {frame_counter}: {labels}")
        
        # Clean up the frame file after processing
        os.remove(frame_filename)
        print(f"Frame {frame_counter} file deleted from /tmp")

    video.release()
    logger.info(f'Total frames analyzed: {frame_counter}')
    print(f"Frame analysis completed for {frame_counter} frames.")
    return video_labels


# def analyze_frames(video_file, context, frame_limit=2):
#     """
#     Analyzes frames in the video file using Amazon Rekognition. 
#     Limits the analysis to a specified number of frames for faster testing.
    
#     Args:
#     - video_file: Path to the video file.
#     - frame_limit: Number of frames to analyze (default is 2).
    
#     Returns:
#     - video_labels: A list of labels detected for each frame.
#     """
#     print(f"Starting frame analysis for {video_file} (Limit: {frame_limit} frames)")
#     video = cv2.VideoCapture(video_file)
#     frame_counter = 0
#     video_labels = []
    
#     while video.isOpened() and frame_counter < frame_limit:
#         ret, frame = video.read()
#         if not ret:
#             print(f"End of video reached after {frame_counter} frames.")
#             break
        
#         frame_counter += 1
#         # Use aws_request_id to create unique file paths
#         frame_filename = f'/tmp/frame_{frame_counter}_{context.aws_request_id}.jpg'
#         cv2.imwrite(frame_filename, frame)
#         print(f"Frame {frame_counter} saved as {frame_filename}")
        
#         with open(frame_filename, 'rb') as image:
#             rekognition_response = rekognition.detect_labels(
#                 Image={'Bytes': image.read()}, MaxLabels=10, MinConfidence=70
#             )
#             labels = [label['Name'] for label in rekognition_response['Labels']]
#             video_labels.append({f'Frame {frame_counter}': labels})
#             print(f"Rekognition labels for frame {frame_counter}: {labels}")
        
#         os.remove(frame_filename)
#         print(f"Frame {frame_counter} file deleted from /tmp")

#     video.release()
#     logger.info(f'Total frames analyzed: {frame_counter}')
#     print(f"Frame analysis completed for {frame_counter} frames.")
#     return video_labels


def handler(event, context):
    response_data = {}
    try:
        print("Event received: ", json.dumps(event, indent=4))
        
        for record in event['Records']:
            bucket_name = record['s3']['bucket']['name']
            object_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            print(f"Processing video file: {object_key} from bucket: {bucket_name}")
            
            # Download the video file from S3
            video_file = f'/tmp/{os.path.basename(object_key)}_{context.aws_request_id}'
            s3_client.download_file(bucket_name, object_key, video_file)
            print(f"Video downloaded to {video_file}")

            # Analyze frames in the video
            video_labels = analyze_frames(video_file, context)
            labels_s3_key = f'{os.path.basename(object_key)}_labels_{context.aws_request_id}.json'
            labels_tmp_file = f'/tmp/video_labels_{context.aws_request_id}.json'
            
            with open(labels_tmp_file, 'w') as f:
                json.dump(video_labels, f)
            print(f"Video labels saved to {labels_tmp_file}")
            
            s3_client.upload_file(labels_tmp_file, frames_bucket, labels_s3_key)
            print(f"Labels file uploaded to S3: {labels_s3_key}")

            # Start transcription job with Amazon Transcribe
            transcription_job_name = f'{os.path.basename(object_key)}_transcription_{context.aws_request_id}'
            print(f"Generated unique transcription job name: {transcription_job_name}")

            transcribe.start_transcription_job(
                TranscriptionJobName=transcription_job_name,
                Media={'MediaFileUri': f's3://{bucket_name}/{object_key}'},
                MediaFormat='mp4',  # Assuming the file format is mp4
                LanguageCode='en-US',
                OutputBucketName=audio_bucket  # S3 bucket to store transcription results
            )
            logger.info(f'Transcription job {transcription_job_name} started')
            print(f"Transcription job started for: {transcription_job_name}")

            # Clean up temp file after upload
            os.remove(labels_tmp_file)

            # Build a structured response
            response_data = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Video processed successfully, transcription job started.',
                    'labels_s3_key': labels_s3_key,
                    'transcription_job_name': transcription_job_name
                })
            }
            print("Process completed successfully.")

    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        print(f"Error encountered: {str(e)}")
        response_data = {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Failed to process video or start transcription job.',
                'error': str(e)
            })
        }

    return response_data
