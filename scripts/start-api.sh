#! /bin/sh

echo "Start script executing for api.."

function configure_container_role(){
    aws configure set default.region eu-west-2
}

function run_celery(){
    cd $DIR_API;
    . $VENV_API/bin/activate && make run-celery &
}

function run_api(){
    cd $DIR_API;
    . $VENV_API/bin/activate && flask run -p 6011 --host=0.0.0.0
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do echo 'Debug mode active..'; sleep 30; done
else
    configure_container_role
    run_celery
    run_api
fi
