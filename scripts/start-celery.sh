#! /bin/sh

echo "Start script executing for celery beat.."

# Query the fixed container agent IP address for credentials (search the AWS docs
# for "Task IAM role" for more information about this endpoint)
session_tokens=$(curl 169.254.170.2$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)

if [[ -z $CONTAINER_ROLE ]] || [[ "$CONTAINER_ROLE" == "" ]]; then
  export CONTAINER_ROLE=$(echo $session_tokens | jq -j .RoleArn)
fi

function configure_container_role(){
  aws configure set role_arn $CONTAINER_ROLE
  aws configure set credential_source EcsContainer
  aws configure set default.region eu-west-2
}

function run_celery(){
  cd $API_DIR;
  . $VENV_API/bin/activate && make run-celery &
}

function run_celery_beat(){
  cd $API_DIR;
  . $VENV_API/bin/activate && make run-celery-beat
}

configure_container_role
run_celery
run_celery_beat
