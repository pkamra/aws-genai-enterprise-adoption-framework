# Stage 1: Build the base image with dependencies
FROM public.ecr.aws/lambda/python:3.10 as base

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


# Stage 2: Build the final Lambda image
FROM base AS final
WORKDIR ${LAMBDA_TASK_ROOT}

RUN echo $(pwd)

COPY main.py requirements.txt ${LAMBDA_TASK_ROOT}/
#COPY helpers ${LAMBDA_TASK_ROOT}/helpers

RUN PYTHON_VERSION=$(python3 --version | cut -d " " -f 2 | cut -d "." -f 1-2) && \
    pip install -r requirements.txt -t /var/lang/lib/python${PYTHON_VERSION}/site-packages/

ENV PATH="/var/task/venv/bin:${PATH}"
CMD [ "main.handler" ]


