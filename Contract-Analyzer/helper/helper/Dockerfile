FROM public.ecr.aws/lambda/python:3.12

# Copy and install Python deps into the Lambda task root so they're on sys.path at runtime
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN python -m pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt -t ${LAMBDA_TASK_ROOT}

# Copy your code
COPY . ${LAMBDA_TASK_ROOT}/

# Lambda handler
CMD ["lambda_function.lambda_handler"]
