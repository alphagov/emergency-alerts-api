#! /bin/sh

echo "Start script executing for migrations.."

VERSION_FILE=$(cat $DIR_API/migrations/.current-alembic-head)

function run_db_upgrade(){
    cd $DIR_API;
    . $VENV_API/bin/activate

    local remote_version=$(flask db current | tail -1 | cut -f1 -d "_")
    local local_version=$(echo $VERSION_FILE | cut -f1 -d "_")

    echo "
    Local migration version: $local_version
    Remote migration version: $remote_version
    "

    STATUS=""
    if [[ $local_version > $remote_version ]]; then
        if flask db upgrade; then
            STATUS="Success performing database upgrade."
            put_success_metric
        else
            STATUS="Error performing database upgrade."
            put_fail_metric
        fi
    else
        STATUS="DB is up to date, no changes needed."
        put_success_metric
    fi

    echo "Migration status: $STATUS"
    echo "New remote migration version: $(flask db current | tail -1 | cut -f1 -d "_")"
}

function put_success_metric(){
    aws cloudwatch put-metric-data \
    --namespace ECS/ContainerInsights \
    --metric-name MigrationSuccess \
    --unit Count \
    --value 1 \
    --dimensions ClusterName=eas-app-cluster,ServiceName=eas-app-migrations,Version=$VERSION_FILE \
    && echo "Created a success metric.." || echo "Unable to create a success metric.."
}

function put_fail_metric(){
    aws cloudwatch put-metric-data \
    --namespace ECS/ContainerInsights \
    --metric-name MigrationFailure \
    --unit Count \
    --value 1 \
    --dimensions ClusterName=eas-app-cluster,ServiceName=eas-app-migrations,Version=$VERSION_FILE \
    && echo "Created a fail metric.." || echo "Unable to create a fail metric.."
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do echo 'Debug mode active..'; sleep 30; done
else
    run_db_upgrade
    echo "Migration script complete."
fi
