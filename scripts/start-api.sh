#! /bin/sh

echo "Start script executing for api.."

# Query the fixed container agent IP address for credentials (search the AWS docs
# for "Task IAM role" for more information about this endpoint)
session_tokens=$(curl 169.254.170.2$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)

if [[ -z $AWS_ACCESS_KEY_ID ]] || [[ "$AWS_ACCESS_KEY_ID" == "" ]]; then
  export AWS_ACCESS_KEY_ID=$(echo $session_tokens | jq -j .AccessKeyId)
fi

if [[ -z $AWS_SECRET_ACCESS_KEY ]] || [[ "$AWS_SECRET_ACCESS_KEY" == "" ]]; then
  export AWS_SECRET_ACCESS_KEY=$(echo $session_tokens | jq -j .SecretAccessKey)
fi

if [[ -z $AWS_SESSION_TOKEN ]] || [[ "$AWS_SESSION_TOKEN" == "" ]]; then
  export AWS_SESSION_TOKEN=$(echo $session_tokens | jq -j .Token)
fi

function run_celery(){
  cd $API_DIR;
  . $VENV_API/bin/activate && make run-celery &
}

function run_api(){
  cd $API_DIR;
  . $VENV_API/bin/activate && flask run -p 6011 --host=0.0.0.0
}

run_celery
run_api
