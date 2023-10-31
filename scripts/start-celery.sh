#! /bin/sh
timestamp_filename='/eas/emergency-alerts-api/celery-beat-healthcheck'
echo "Start script executing for celery beat.."

function configure_container_role(){
  aws configure set default.region eu-west-2
}

function run_celery(){
  cd $DIR_API;
  . $VENV_API/bin/activate && make run-celery &
}

function run_celery_beat(){
  cd $DIR_API;
  . $VENV_API/bin/activate && make run-celery-beat
}

function update_timestamp(){
    echo $(date +%s) > $timestamp_filename
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do
        echo 'Debug mode active..';
        update_timestamp
        sleep 10;
    done
else
  configure_container_role
  run_celery
  run_celery_beat
fi

