@echo off
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 730335331118.dkr.ecr.us-west-2.amazonaws.com
docker build -t worddocgenerator2 ./worddocGenerator2 --provenance=false
docker tag worddocgenerator2:latest 730335331118.dkr.ecr.us-west-2.amazonaws.com/worddocgenerator2:latest
docker push 730335331118.dkr.ecr.us-west-2.amazonaws.com/worddocgenerator2:latest