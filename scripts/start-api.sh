#! /bin/sh

echo "Start script executing for api.."

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
