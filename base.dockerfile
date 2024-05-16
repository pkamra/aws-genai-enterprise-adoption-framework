FROM public.ecr.aws/lambda/python:3.11

RUN yum update -y
RUN yum install -y wget tar gzip libXinerama dbus-libs cairo cups-libs unoconv python3 python3-pip java-1.8.0-openjdk

RUN python3 -m venv venv && \
    venv/bin/pip install --upgrade pip && \
    venv/bin/pip install --no-cache-dir awslambdaric boto3
ENV PATH="/var/task/venv/bin:${PATH}"

WORKDIR /usr/local

# This link can be out of date. Check the latest version at https://www.libreoffice.org/download/download/
RUN wget https://downloadarchive.documentfoundation.org/libreoffice/old/7.5.5.2/rpm/x86_64/LibreOffice_7.5.5.2_Linux_x86-64_rpm.tar.gz
RUN tar -xzf LibreOffice_7.5.5.2_Linux_x86-64_rpm.tar.gz
WORKDIR /usr/local/LibreOffice_7.5.5.2_Linux_x86-64_rpm/RPMS
RUN yum localinstall *.rpm -y
RUN rm -rf /usr/local/LibreOffice_7.5.5.2_Linux_x86-64_rpm.tar.gz /usr/local/LibreOffice_7.5.5.2_Linux_x86-64_rpm

# Set environment variables for LibreOffice
ENV PATH="/usr/local/LibreOffice_7.5.5.2_Linux_x86-64_rpm/RPMS/desktop-integration:${PATH}"
ENV LIBREOFFICE_PATH="/usr/local/LibreOffice_7.5.5.2_Linux_x86-64_rpm/RPMS/desktop-integration"

# The following two lines are for local testing
# ENTRYPOINT []
# CMD ["tail", "-f", "/dev/null"]

# The following two lines create and push the image to ECR
COPY main.py ${LAMBDA_TASK_ROOT}
CMD ["main.handler"]

# The following steps assist with creating and deploying the docker image based on this Dockerfile (base.dockerfile).
#
# 1. Retrieve an authentication token and authenticate your Docker client to your registry. Use the AWS CLI:
#
#       aws ecr get-login-password --region <YOUR_REGION> | docker login --username AWS --password-stdin <YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com
#
# 2. Build image:
#
#       docker build -f <Dockerfile_name> -t <base_image_name> <build_context>
# 
# 3. Tag image:
#       
#       docker tag <base_image_name>:latest <YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com/<ecr_repo_name>:base
#
# OPTIONAL: aws ecr batch-delete-image --repository-name <ecr_repo_name --image-ids imageTag=base
# 
# 4. Push image to ECR:
#
#       docker push <YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_REGION>.amazonaws.com/<ecr_repo_name>:base
#