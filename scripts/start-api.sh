#! /bin/sh

echo "Start script executing for api.."

function run_db_upgrade(){
  cd $API_DIR;
  . $VENV_API/bin/activate

  local head=$(flask db heads | tail -1)
  local current=$(flask db current | tail -1)

  # Checking if the database upgrade has been previously been completed to avoid running multiple times.
  if [[ $head != $current ]]; then
    echo "Run DB migration"
    flask db upgrade
  else
    echo "DB is up to date"
  fi

  echo $(flask db current)
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
if [[ ! -z $MASTER_USERNAME ]]; then
  run_db_upgrade
else
  run_celery
  run_api
fi
