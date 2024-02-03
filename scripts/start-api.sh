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

function is_expected_migration_greater_than_db(){
    sleep 2
    current_db_version_full=$(curl http://0.0.0.0:6011/_api_status | jq .db_version | tr -d '"')
    current_db_version=$(echo $current_db_version_full | cut -d'_' -f1)

    current_local_version_full=$(cat /eas/emergency-alerts-api/migrations/.current-alembic-head)
    current_local_version=$(echo $current_local_version_full | cut -d'_' -f1)

    if [ $current_db_version -lt $current_local_version ]; then
        echo "Database version needs to be upgraded to use this migration version."
        echo ""
        echo "Current database version: $current_db_version_full"
        echo "Current local version: $current_local_version_full"
        sleep 2
        shutdown -h now
    fi
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do echo 'Debug mode active..'; sleep 30; done
else
    configure_container_role
    run_api
    run_celery
    # is_expected_migration_greater_than_db  # TODO: Needs some work for migrations pipeline
fi
