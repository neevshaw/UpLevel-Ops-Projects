@echo off
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 730335331118.dkr.ecr.us-west-2.amazonaws.com
docker build -t blvdcontract2 ./helper --provenance=false
docker tag blvdcontract2:latest 730335331118.dkr.ecr.us-west-2.amazonaws.com/blvdcontract2:latest
docker push 730335331118.dkr.ecr.us-west-2.amazonaws.com/blvdcontract2:latest