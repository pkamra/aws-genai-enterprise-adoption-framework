import json
import os
import logging
import boto3
import fitz  # PyMuPDF library for PDF processing
from PIL import Image
import re
import shutil
import time
import urllib

from botocore.config import Config


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# Initialize S3 and SQS clients
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
queue_url = os.environ['SQS_QUEUE_URL']  # The SQS queue URL
output_bucket = os.environ['OUTPUT_BUCKET']

# Set custom timeout
config = Config(connect_timeout=300, read_timeout=300)  # Increase timeouts as needed

# Initialize Bedrock Runtime client with a custom timeout configuration
bedrock_runtime = boto3.client('bedrock-runtime', region_name=os.environ['AWS_REGION'], config=config)

# # Base inference parameters to use.
inferenceConfig={"maxTokens": 4096, "temperature": 0.0, "topP": 0.45}

# # Function to invoke Bedrock API with a delay between calls
# def invoke_with_delay(model_id, messages, delay=10):
#     try:
#         response = bedrock_runtime.converse(
#             modelId=model_id,
#             inferenceConfig=inferenceConfig,
#             messages=messages
#         )
#         token_usage = response['usage']
#         print(f"Input tokens: {token_usage['inputTokens']}")
#         print(f"Output tokens: {token_usage['outputTokens']}")
#         print(f"Total tokens: {token_usage['totalTokens']}")
#         print(f"Stop reason: {response['stopReason']}")
#         return response
#     except Exception as e:
#         print(f"Error encountered: {str(e)}")
#         raise Exception(f"ModelInvocationException: Failed during invoke_model.") from e

def invoke_with_delay(model_id, messages, delay=10, max_retries=3):
    retries = 0
    while retries < max_retries:
        try:
            response = bedrock_runtime.converse(
                modelId=model_id,
                inferenceConfig=inferenceConfig,
                messages=messages
            )
            # Log token usage.
            token_usage = response['usage']
            # logger.info("Input tokens: %s", token_usage['inputTokens'])
            # logger.info("Output tokens: %s", token_usage['outputTokens'])
            # logger.info("Total tokens: %s", token_usage['totalTokens'])
            # logger.info("Stop reason: %s", response['stopReason'])
            print(f"Input tokens: {token_usage['inputTokens']}")
            print(f"Output tokens: {token_usage['outputTokens']}")
            print(f"Total tokens: {token_usage['totalTokens']}")
            print(f"Stop reason: {response['stopReason']}")
            return response
        except Exception as e:
            # If it's a timeout error, retry after a delay
            if isinstance(e, ReadTimeoutError):
                retries += 1
                # logger.warning(f"Timeout occurred. Retry {retries} of {max_retries}. Waiting {delay} seconds.")
                print(f"Timeout occurred. Retry {retries} of {max_retries}. Waiting {delay} seconds.")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                # logger.error(f"Error encountered: {str(e)}")
                print(f"Error encountered: {str(e)}")
                raise Exception(f"ModelInvocationException: Failed during invoke_model.") from e
    
    raise Exception("Max retries exceeded. Bedrock model failed to respond.")

# Resize and reduce image size progressively if an error occurs
def resize_image_by_scale(image_path, reduce_by=0.9):
    img = Image.open(image_path)
    width, height = img.size
    new_width = int(width * reduce_by)
    new_height = int(height * reduce_by)
    img = img.resize((new_width, new_height), Image.LANCZOS)
    img.save(image_path)
    return img

# Function to handle model invocation with error handling and resizing logic
def invoke_model_with_resizing(image_path, messages, model_id, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            response = invoke_with_delay(model_id, messages)
            return response
        except Exception as e:
            if "image exceeds" in str(e) or "Image exceeds max pixels allowed" in str(e):
                # logger.warning(f"Image size issue detected on retry {retries + 1}. Resizing image: {image_path}")
                print(f"Image size issue detected on retry {retries + 1}. Resizing image: {image_path}")
                resize_image_by_scale(image_path)
            else:
                raise e
        retries += 1
    raise Exception(f"Max retries exceeded for image {image_path}")

# Resize the image to ensure it fits within the allowed pixel limits when converting PDF to PNG
def resize_image_initial(image_path, max_width=1024, max_height=1024):
    img = Image.open(image_path)
    width, height = img.size
    aspect_ratio = width / height
    if width > max_width or height > max_height:
        if width > height:
            new_width = max_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = max_height
            new_width = int(new_height * aspect_ratio)
        img = img.resize((new_width, new_height), Image.LANCZOS)
        img.save(image_path)
    return img

# Convert PDF to PNG and resize the image to fit within the pixel limit
def pdf_to_png(pdf_file, output_folder, dpi=150, max_width=1024, max_height=1024):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    pdf_document = fitz.open(pdf_file)
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        zoom_matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
        image_path = os.path.join(output_folder, f"page_{page_num+1}.png")
        pix.save(image_path)
        resize_image_initial(image_path, max_width=max_width, max_height=max_height)
    pdf_document.close()

# Function to extract page number from filename
def extract_page_number(filename):
    match = re.search(r"page_(\d+)\.png", filename)
    if match:
        return int(match.group(1))
    return float('inf')

# Check if the last element is a table (on previous page)
def check_if_last_element_is_table(image_path):
    with open(image_path, "rb") as f:
        image = f.read()
    messages = [
        {"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": image}}}, {"text": """Check the last visible content on this page and 
        confirm if the last element (before any page footer) is a table. Answer 'Yes' if it is, 'No' otherwise."""}]}
    ]
    response = invoke_with_delay(model_id="anthropic.claude-3-sonnet-20240229-v1:0", messages=messages)
    return "Yes" in response["output"]["message"]["content"][0]["text"]

# Check if the first element is a table (on the current page)
def check_if_first_element_is_table(image_path):
    with open(image_path, "rb") as f:
        image = f.read()
    messages = [
        {"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": image}}}, {"text": """Check the first visible content on this page and 
        confirm if the first element (after any page header) is a table. Answer 'Yes' if it is, 'No' otherwise."""}]}
    ]
    response = invoke_with_delay(model_id="anthropic.claude-3-sonnet-20240229-v1:0", messages=messages)
    return "Yes" in response["output"]["message"]["content"][0]["text"]

# Process the page using Bedrock model
def process_subsequent_pages(previous_text, image_path, include_previous, model_id):
    with open(image_path, "rb") as f:
        image = f.read()
    if include_previous:
        user_message = f"""
Transcribe the text content from the provided image page and output in Markdown syntax (not code blocks). 
The text from the previous page is provided for reference. Follow these steps:

1. Examine the provided page carefully, using the provided text from the previous page as reference for continuing any incomplete elements (e.g., tables or paragraphs).

2. Identify all elements present in the page, including headers, body text, footnotes, tables, visualizations, captions, and page numbers, etc.

3. Use markdown syntax to format your output:
    - Headings: # for main, ## for sections, ### for subsections, etc.
    - Lists: * or - for bulleted, 1. 2. 3. for numbered
    - Do not repeat yourself

4. If the element is a visualization
    - Provide a detailed description in natural language
    - Do not transcribe text in the visualization after providing the description

5. If the element is a table or table of contents
    - Create a markdown table, ensuring every row has the same number of columns
    - Maintain cell alignment as closely as possible
    - Do not split a table into multiple tables
    - If a merged cell spans multiple rows or columns, place the text in the top-left cell and output ' ' for other cells.
    - Use | for column separators, |-|-| for header row separators
    - If a cell has multiple items, list them in separate rows
    - If the table contains sub-headers, separate the sub-headers from the headers in another row

6. If the element is a paragraph
    - Transcribe each text element verbatim as it appears, without skipping any word.

7. If the element is a header, footer, footnote, page number
    - Transcribe each text element verbatim as it appears, without skipping any word.

Output Example:

A bar chart showing annual sales figures, with the y-axis labeled "Sales ($Million)" and the x-axis labeled "Year". The chart has bars for 2018 ($12M), 2019 ($18M), 2020 ($8M), and 2021 ($22M).
Figure 3: This chart shows annual sales in millions. The year 2020 was significantly down due to the COVID-19 pandemic.

# Annual Report

## Financial Highlights

* Revenue: $40M
* Profit: $12M
* EPS: $1.25


| | Year Ended December 31, | |
| | 2021 | 2022 |
|-|-|-|
| Cash provided by (used in): | | |
| Operating activities | $ 46,327 | $ 46,752 |
| Investing activities | (58,154) | (37,601) |
| Financing activities | 6,291 | 9,718 |


Here is the text from the previous page for reference to continue any incomplete elements (e.g., tables or paragraphs) :

{previous_text}

And here is the image of the next page.
"""
    else:
        user_message = """Transcribe the text content from an image page and output in Markdown syntax (not code blocks). Follow these steps:

1. Examine the provided page carefully.

2. Identify all elements present in the page, including headers, body text, footnotes, tables, visualizations, captions, and page numbers, etc.

3. Use markdown syntax to format your output:
    - Headings: # for main, ## for sections, ### for subsections, etc.
    - Lists: * or - for bulleted, 1. 2. 3. for numbered
    - Do not repeat yourself

4. If the element is a visualization
    - Provide a detailed description in natural language
    - Do not transcribe text in the visualization after providing the description

5. If the element is a table or table of contents
    - Create a markdown table, ensuring every row has the same number of columns
    - Maintain cell alignment as closely as possible
    - Do not split a table into multiple tables
    - If a merged cell spans multiple rows or columns, place the text in the top-left cell and output ' ' for other cells
    - Use | for column separators, |-|-| for header row separators
    - If a cell has multiple items, list them in separate rows
    - If the table contains sub-headers, separate the sub-headers from the headers in another row

6. If the element is a paragraph
    - Transcribe each text element verbatim  as it appears, without skipping any word.

7. If the element is a header, footer, footnote, page number
    - Transcribe each text element verbatim as it appears, without skipping any word.

Output Example:

A bar chart showing annual sales figures, with the y-axis labeled "Sales ($Million)" and the x-axis labeled "Year". The chart has bars for 2018 ($12M), 2019 ($18M), 2020 ($8M), and 2021 ($22M).
Figure 3: This chart shows annual sales in millions. The year 2020 was significantly down due to the COVID-19 pandemic.

# Annual Report

## Financial Highlights

* Revenue: $40M
* Profit: $12M
* EPS: $1.25


| | Year Ended December 31, | |
| | 2021 | 2022 |
|-|-|-|
| Cash provided by (used in): | | |
| Operating activities | $ 46,327 | $ 46,752 |
| Investing activities | (58,154) | (37,601) |
| Financing activities | 6,291 | 9,718 |

Here is the image.
"""
    messages = [{"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": image}}}, {"text": user_message}]}]
    response = invoke_model_with_resizing(image_path, messages, model_id)
    return response["output"]["message"]["content"][0]["text"]

# Handle SQS message re-triggering the lambda
# def handle_sqs_trigger(event):
#     body = json.loads(event['Records'][0]['body'])
#     return body['page_counter'], body['previous_text'], body['source_bucket'], body['source_key'], body['s3_output_key']  # Extract s3_output_key

def handle_sqs_trigger(event):
    # Extract and decode the SQS body from the event
    try:
        sqs_body = event['Records'][0]['body']
        # Parse the JSON string inside the body
        body = json.loads(sqs_body)
        print(f"SQS body: {body}")
        return body['page_counter'], body['previous_text'], body['source_bucket'], urllib.parse.unquote_plus(body['source_key']), urllib.parse.unquote_plus(body['s3_output_key'])
    except KeyError as e:
        print(f"KeyError occurred while parsing SQS body: {str(e)}")
        raise ValueError("Invalid SQS message structure")
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        raise ValueError("Failed to parse SQS message body")
        
# Send SQS message when the function is about to timeout
def send_sqs_message(source_bucket, source_key, s3_output_key, page_counter, previous_text):
    message_body = {
        "source_bucket": source_bucket,
        "source_key": source_key,
        "page_counter": page_counter,
        "previous_text": previous_text,
        "s3_output_key": s3_output_key  # Add this to the SQS message
    }
    sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message_body))

# Add the logic to append the contents of the Lambda's local output file to the existing S3 file:
def append_to_s3_file(output_bucket, s3_output_key, local_file_path):
    try:
        # Check if the S3 file exists using list_objects_v2
        response = s3_client.list_objects_v2(Bucket=output_bucket, Prefix=s3_output_key)
        file_exists = any(obj['Key'] == s3_output_key for obj in response.get('Contents', []))

        if file_exists:
            print(f"S3 file {s3_output_key} exists. Appending content.")

            # If the file exists, download it to a local path
            s3_temp_path = f'/tmp/s3-{os.path.basename(s3_output_key)}'
            s3_client.download_file(output_bucket, s3_output_key, s3_temp_path)
            print(f"Downloaded existing S3 file to {s3_temp_path}")

            # Append the local file content to the S3 file
            with open(s3_temp_path, 'a') as s3_file, open(local_file_path, 'r') as local_file:
                s3_file.write(local_file.read())
            print(f"Appended local content to the existing S3 file {s3_output_key}")

            # Upload the updated file back to S3
            s3_client.upload_file(s3_temp_path, output_bucket, s3_output_key)
            print(f"Uploaded updated file to S3: {s3_output_key}")
        else:
            print(f"S3 file {s3_output_key} does not exist. Uploading as new file.")

            # If the file doesn't exist, upload the local file as the S3 object
            s3_client.upload_file(local_file_path, output_bucket, s3_output_key)
            print(f"Uploaded new file to S3: {s3_output_key}")

    except Exception as e:
        print(f"Error appending or uploading to S3 file: {str(e)}")
        raise

# Main function to process the PDF and write to a single text file (with SQS for progress tracking)
def process_pdf(pdf_file, output_file_path, source_bucket, source_key, s3_output_key, page_counter=0, previous_text="", context=None):
    
    # Use the Lambda's unique request ID to ensure a unique output folder for each invocation
    output_folder = f'/tmp/png-output-{context.aws_request_id}/'
    logger.info("pdf to png initial start")
    pdf_to_png(pdf_file, output_folder)
    logger.info("pdf to png initial end" )

    # Get PNG files in the folder
    png_files = [os.path.join(output_folder, filename) for filename in os.listdir(output_folder) if filename.endswith(".png")]
    png_files = sorted(png_files, key=extract_page_number)

    with open(output_file_path, "a") as output_file:
        for idx in range(page_counter, len(png_files)):
            print(f"Page counter : {idx+1}")
            is_table_previous = check_if_last_element_is_table(png_files[idx - 1]) if idx > 0 else False
            is_table_current = check_if_first_element_is_table(png_files[idx])
            include_previous = is_table_previous and is_table_current
            content_text = process_subsequent_pages(previous_text, png_files[idx], include_previous, "anthropic.claude-3-sonnet-20240229-v1:0")
            previous_text = content_text
            # Log the values of is_table_previous, is_table_current, and include_previous
            print(f"is_table_previous: {is_table_previous}, is_table_current: {is_table_current}, include_previous: {include_previous}")

            output_file.write(f"Page {idx + 1}\n{content_text}\n\n")
            
            
            # Check Lambda remaining time
            remaining_time = context.get_remaining_time_in_millis()
            if remaining_time < 120000:  # If less than 2 mins remaining
                print(f"Sending to SQS queue with values :: S3 bucket {source_bucket}, source_key {source_key}, s3_output_key {s3_output_key}, idx + 1 {idx + 1}, previous_text {previous_text}")
                send_sqs_message(source_bucket, source_key, s3_output_key, idx + 1, previous_text)  # Send progress to SQS
                break

    shutil.rmtree(output_folder)
    print(f"Processing completed. Output saved to : {output_file_path}")

# Lambda function handler
def handler(event, context):
    
    # Initialize variables
    source_bucket = None
    source_key = None
    page_counter = 0
    previous_text = ""
    s3_output_key = ""
    print(json.dumps(event, indent=4))

    
    # Handle SQS or S3 event
    if 'Records' in event and 's3' in event['Records'][0]:
        # S3 Event Trigger
        source_bucket = event['Records'][0]['s3']['bucket']['name']
        source_key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        page_counter, previous_text = 0, ""
        s3_output_key = f"{source_key}.txt"
        print(f"S3 Event Trigger source_key :: {source_key}, s3_output_key {source_key}.txt")
        
    else:
        # SQS Event Trigger
        print(".....SQS event detected.....")
        try:
            page_counter, previous_text, source_bucket, source_key, s3_output_key = handle_sqs_trigger(event)
            print(f"Extracted from SQS: source_bucket: {source_bucket}, source_key: {source_key}, s3_output_key: {s3_output_key}")
            
            # Manually delete the SQS message after processing
            receipt_handle = event['Records'][0]['receiptHandle']
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            print(f"Deleted SQS message with ReceiptHandle: {receipt_handle}")
        except ValueError as e:
            print(f"Error processing SQS message: {str(e)}")
            raise


    # Check if source_key is valid before proceeding
    if not source_key:
        raise ValueError("Source key is missing or invalid")
    # Download the PDF file from S3
    pdf_file = f'/tmp/{os.path.basename(source_key)}'
    s3_client.download_file(source_bucket, source_key, pdf_file)

    # Output text file path
    output_file_path = f'/tmp/output-text-file-{context.aws_request_id}.txt'
    
    # Process the PDF with progress tracking
    process_pdf(pdf_file, output_file_path, source_bucket, source_key, s3_output_key, page_counter, previous_text, context)

    # Append local output to the existing S3 output file and upload the updated file
    append_to_s3_file(output_bucket, s3_output_key, output_file_path)
    
    return {'statusCode': 200, 'body': json.dumps('Processing completed successfully.')}
