# Use the AWS Lambda Python 3.12 base image
FROM public.ecr.aws/lambda/python:3.12

# Copy and install dependencies
COPY requirements.txt  .
# Always upgrade pip in container to avoid outdated resolver issues
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Ensure these common libraries are available even if missing from requirements.txt
RUN python -m pip install --no-cache-dir requests boto3

# Copy application code into Lambda task root
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
COPY word_doc.py ${LAMBDA_TASK_ROOT}/

# Lambda entrypoint
CMD ["lambda_function.lambda_handler"]
