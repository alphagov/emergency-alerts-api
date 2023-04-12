#! /bin/sh

echo "Start script executing for api.."

function run_db_upgrade(){
  cd $API_DIR;
  . $VENV_API/bin/activate
  # take last line to trim the logging output
  local head=$(flask db heads | tail -1)
  local current=$(flask db current | tail -1)
  if [[ $head != $current ]]; then
    echo "Run DB migration"
    flask db upgrade
  else
    echo "DB is up to date"
  fi
  echo $(flask db current)
  unset MASTER_USERNAME
  unset MASTER_PASSWORD
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

configure_container_role
run_db_upgrade
run_celery
run_api
