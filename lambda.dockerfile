# To build from ECR
FROM 239380694500.dkr.ecr.us-east-1.amazonaws.com/globe-pptx-converter:base

# To build from locally stored directory
# FROM base-image:latest

WORKDIR ${LAMBDA_TASK_ROOT}

RUN echo $(pwd)

COPY main.py requirements.txt ${LAMBDA_TASK_ROOT}/

RUN PYTHON_VERSION=$(python3 --version | cut -d " " -f 2 | cut -d "." -f 1-2) && \
    pip install -r requirements.txt -t /var/lang/lib/python${PYTHON_VERSION}/site-packages/

ENV PATH="/var/task/venv/bin:${PATH}"

CMD [ "main.handler" ]

# To access the container locally, remove the preceding command and uncomment to following two
# ENTRYPOINT []
# CMD ["tail", "-f", "/dev/null"]

# The following steps assist with creating and deploying the docker image based on this Dockerfile (lambda.dockerfile).
#
# 1. Retrieve an authentication token and authenticate your Docker client to your registry. Use the AWS CLI:
#
#       aws ecr get-login-password --region <YOUR_REGION> | docker login --username AWS --password-stdin <YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com
#
# 2. Build image:
#       
#       docker build -f <Dockerfile_name> -t <lambda_image_name> <build_context>
# 
# 3. Tag image:
#       
#       docker tag <lambda_image_name>:latest <YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com/<ecr_repo_name>:lambda
#
# OPTIONAL: aws ecr batch-delete-image --repository-name <ecr_repo_name --image-ids imageTag=lambda 
# 
# 4. Push image to ECR:
#
#       docker push <YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com/<ecr_repo_name>:lambda
#