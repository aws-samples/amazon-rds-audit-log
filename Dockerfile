FROM public.ecr.aws/lambda/python:3.9
# Install the function's dependencies using file requirements.txt
# from your project folder.
#checkov:skip=CKV_DOCKER_3: no need to check
#checkov:skip=CKV_DOCKER_2: no need to check
COPY requirements.txt  requirements.txt
RUN  pip3 install -r requirements.txt
COPY lambda lambda
