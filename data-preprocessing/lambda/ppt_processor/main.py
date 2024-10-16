import boto3
import subprocess
import os

# Ensure the /tmp directory exists
os.makedirs("/tmp", exist_ok=True)

print(os.listdir('/tmp'))

# Set the environment variables for LibreOffice
os.environ['PATH'] = "/opt/libreoffice7.5/program:" + os.environ['PATH']

def convert_to_pdf(file):
    print("Starting conversion to PDF...")
    output_file = os.path.splitext(file)[0] + '.pdf'
    result = subprocess.run(['/opt/libreoffice7.5/program/soffice', '--headless', '--nologo', '--nodefault', '--nofirststartwizard', '--convert-to', 'pdf', file, '--outdir', '/tmp'], capture_output=True)
    
    if result.returncode != 0:
        print(f"LibreOffice conversion failed with return code: {result.returncode}")
        print(f"stderr: {result.stderr.decode()}")
        print(f"stdout: {result.stdout.decode()}")
        raise Exception("Conversion failed.")
    
    if not os.path.exists(output_file):
        print(os.listdir('/tmp'))
        raise Exception(f"PDF file was not created. LibreOffice stdout: {result.stdout.decode()}, stderr: {result.stderr.decode()}")
    
    print("Conversion to PDF completed.")
    return output_file

def download_from_s3(bucket, key):
    print(f"Downloading {key} from S3...")
    s3 = boto3.client('s3')
    local_file = os.path.join("/tmp", os.path.basename(key))
    s3.download_file(bucket, key, local_file)
    
    if not os.path.exists(local_file):
        raise Exception("File was not downloaded")
    
    print(f"Downloaded {key} from S3.")
    return local_file

def upload_to_s3(bucket, file):
    print(f"Uploading {file} to S3...")
    
    if not os.path.exists(file):
        raise Exception("No such file to upload: " + file)
    
    s3 = boto3.client('s3')
    filename = os.path.basename(file)
    output_key = f"{filename}"
    s3.upload_file(file, bucket, output_key)
    
    print(f"Uploaded {file} to S3 as {output_key}.")

def handler(event, context):
    print("Lambda function triggered by S3 event.")

    # Extract bucket name and object key from the S3 event
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    object_key = event['Records'][0]['s3']['object']['key']

    print(f"Bucket: {bucket_name}, Object Key: {object_key}")

    # Set up the environment for LibreOffice to use the /tmp directory
    os.environ["HOME"] = "/tmp"

    # Download the DOCX file from S3
    docx_file = download_from_s3(bucket_name, object_key)

    # Convert the DOCX file to PDF
    pdf_file = convert_to_pdf(docx_file)

    # Upload the converted PDF to the output S3 bucket
    output_bucket = os.getenv('OUTPUT_BUCKET', 'output-bucket')
    upload_to_s3(output_bucket, pdf_file)  # Use "converted" as the key prefix

    # Clean up the /tmp directory by removing the local files
    os.remove(docx_file)
    os.remove(pdf_file)

    print("Lambda function completed successfully.")
    
    return {
        "statusCode": 200,
        "body": "PDF conversion completed successfully"
    }
