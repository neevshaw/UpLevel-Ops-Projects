@echo off
rem Usage: set AWS_ACCOUNT_ID=<your account id> before running. Optionally set AWS_REGION (default us-west-2).
if "%AWS_ACCOUNT_ID%"=="" (
    echo AWS_ACCOUNT_ID is not set.
    exit /b 1
)
if "%AWS_REGION%"=="" set AWS_REGION=us-west-2
set REGISTRY=%AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com

aws ecr get-login-password --region %AWS_REGION% | docker login --username AWS --password-stdin %REGISTRY%
docker build -t blvdcontract2 ./helper --provenance=false
docker tag blvdcontract2:latest %REGISTRY%/blvdcontract2:latest
docker push %REGISTRY%/blvdcontract2:latest
