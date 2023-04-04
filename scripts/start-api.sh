#! /bin/sh

echo "Start script executing for api.."

# Query the fixed container agent IP address for credentials (search the AWS docs
# for "Task IAM role" for more information about this endpoint)
session_tokens=$(curl 169.254.170.2$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)

if [[ -z $CONTAINER_ROLE ]] || [[ "$CONTAINER_ROLE" == "" ]]; then
  export CONTAINER_ROLE=$(echo $session_tokens | jq -j .RoleArn)
fi

function run_db_upgrade(){
  cd $API_DIR;
  . $VENV_API/bin/activate && flask db upgrade && flask db current
}

function configure_container_role(){
  aws configure set default.region eu-west-2
}

function run_celery(){
  cd $API_DIR;
  . $VENV_API/bin/activate && make run-celery &
}

function run_api(){
  cd $API_DIR;
  . $VENV_API/bin/activate && flask run -p 6011 --host=0.0.0.0
}

if [[ -n $MASTER_USERNAME ]]; then
  run_db_upgrade
else
  configure_container_role
  run_celery
  run_api
fi
