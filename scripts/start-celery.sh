#! /bin/sh

echo "Start script executing for celery beat.."

function configure_container_role(){
  aws configure set default.region ${AWS_REGION:-eu-west-2}
}

function run_celery(){
  echo "$(date +%s)" > "/eas/emergency-alerts-api/celery-beat-healthcheck"
  chown easuser:easuser "/eas/emergency-alerts-api/celery-beat-healthcheck"
  cd $DIR_API;
  . $VENV_API/bin/activate && make run-celery &
}

function run_celery_beat(){
  cd $DIR_API;
  . $VENV_API/bin/activate && make run-celery-beat
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do echo 'Debug mode active..'; sleep 30; done
else
  configure_container_role
  run_celery
  run_celery_beat
fi
