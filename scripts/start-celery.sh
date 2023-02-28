#! /bin/sh

echo "Start script executing for celery beat.."

function run_celery_beat(){
  cd $API_DIR;
  . $VENV_API/bin/activate && make run-celery-beat
}

run_celery_beat
