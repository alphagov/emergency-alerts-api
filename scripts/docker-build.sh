#! /bin/sh

PLATFORM=linux/amd64
# We can add linux/arm64 back in if we need it
REGION='eu-west-2'

while [ $# -gt 0 ]; do
  if [[ $1 == *"--"* ]]; then
    param="${1/--/}"
    declare $param="$2"
  fi
  shift
done

if [[ $ENVIRONMENT == "development" ]]; then
  ECS_ACCOUNT_NUMBER=388086622185
else
  echo "No environment selected"
  exit 1;
fi

function ecr_login(){
  aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECS_ACCOUNT_NUMBER.dkr.ecr.$REGION.amazonaws.com
}

function docker_build(){
  docker buildx build \
    --platform $PLATFORM \
    -t $ECS_ACCOUNT_NUMBER.dkr.ecr.$REGION.amazonaws.com/eas-app-$IMAGE:latest \
    -f Dockerfile.eas-$IMAGE \
    $ARGS \
    .
}

ecr_login
docker_build
