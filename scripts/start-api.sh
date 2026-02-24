#!/usr/bin/env bash
echo "start-api.sh executing"

put_metric_data(){
    if [[ $1 != "Backups" && $1 != "Migrations" ]]; then
        echo "A namespace is required (Backups || Migrations)."
        exit 1;
    fi

    if [[ $2 != "success" && $2 != "failure" ]]; then
        echo "Invalid status type (success || failure)."
        exit 1;
    fi

    if [[ -z $START_TIME ]]; then
        echo "START_TIME is not provided but is required."
        exit 1;
    fi

    if [[ -z $PIPELINE_RUN_ID ]]; then
        echo "PIPELINE_RUN_ID is not provided but is required."
        exit 1;
    fi

    # For future we should add a version e.g. Version=1112_test
    dimension="PipelineRunId=$PIPELINE_RUN_ID,StartTime=$START_TIME,Status=$2"
    simple_dimension="Status=$2" # Just the status dimension; for CloudWatch alarming purposes

    # We have multiple backup buckets, so a third argument can be passed to
    # reflect the particular bucket the backup was pushed to.
    if [[ -n $3 && $1 == "Backups" ]]; then
        simple_dimension="$simple_dimension,Bucket=$3"
    fi

    echo "Putting metric $1[$SERVICE_ACTION] with dimension: $dimension"
    aws cloudwatch put-metric-data \
        --namespace "$1" \
        --metric-name "$SERVICE_ACTION" \
        --dimensions "$dimension" \
        --value 1 \
        --timestamp "$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")" \
        --region "${AWS_REGION:-eu-west-2}"

    aws cloudwatch put-metric-data \
        --namespace "$1" \
        --metric-name "$SERVICE_ACTION" \
        --dimensions "$simple_dimension" \
        --value 1 \
        --timestamp "$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")" \
        --region "${AWS_REGION:-eu-west-2}"
}

run_db_migrations(){
    cd "$DIR_API";
    . $VENV_API/bin/activate

    local head=$(flask db heads | tail -1)
    local current=$(flask db current | tail -1)

    # Checking if the database upgrade has been previously been completed to avoid running multiple times.
    if [[ $head != "$current" ]]; then
        echo "Run DB migration"
        if flask db upgrade; then
            put_metric_data "Migrations" "success"
        else
            put_metric_data "Migrations" "failure"
        fi
    else
        echo "DB is up to date"
        put_metric_data "Migrations" "success"
    fi
}

run_backup_database(){
    if [[ -z $RDS_HOST  ]]; then
        echo "RDS_HOST is not provided but is required."
        put_metric_data "Backups" "failure"
        exit 1;
    fi

    if [[ -z $RDS_PORT  ]]; then
        echo "RDS_PORT is not provided but is required."
        put_metric_data "Backups" "failure"
        exit 1;
    fi

    if [[ -z $DATABASE  ]]; then
        echo "DATABASE name is not provided but is required."
        put_metric_data "Backups" "failure"
        exit 1;
    fi

    if [[ -z $BACKUP_BUCKET_NAMES ]]; then
        echo "BACKUP_BUCKET_NAMES is not provided but is required."
        put_metric_data "Backups" "failure"
        exit 1;
    fi

    if [[ -z $ENVIRONMENT ]]; then
        echo "ENVIRONMENT is not provided but is required."
        put_metric_data "Backups" "failure"
        exit 1;
    fi

    # Must be in /eas as it's owned by easuser
    SQL_FILENAME_SUFFIX=$ENVIRONMENT-$(date -u +"%Y-%m-%d-%H-%M-%S").sql
    SQL_FILENAME=/eas/$SQL_FILENAME_SUFFIX
    rm -f "$SQL_FILENAME"

    echo "Running pg_dump to $SQL_FILENAME"

    # To exclude table use: --exclude-table TABLE_NAME
    PGPASSWORD=$MASTER_PASSWORD pg_dump -h "$RDS_HOST" -p "$RDS_PORT" -U "$MASTER_USERNAME" \
        --file "$SQL_FILENAME" \
        "$DATABASE"

    if [ "$(cat "$SQL_FILENAME" | grep "PostgreSQL database dump" | wc -l)" -lt 2 ]; then
        echo "There was an issue creating the backup.";
        put_metric_data "Backups" "failure"
        exit 1;
    fi

    ARCHIVE_FILENAME_SUFFIX=$SQL_FILENAME_SUFFIX.tar
    ARCHIVE_FILENAME=/eas/$ARCHIVE_FILENAME_SUFFIX
    tar -cf "$ARCHIVE_FILENAME" "$SQL_FILENAME"

    echo "Created $ARCHIVE_FILENAME"
    ls -lh "$ARCHIVE_FILENAME"

    # Upload the backup to S3
    IFS=',' read -ra buckets <<< "$BACKUP_BUCKET_NAMES"

    for bucket in "${buckets[@]}"; do
        if aws s3api put-object \
            --bucket "$bucket" \
            --key "$ENVIRONMENT/$ARCHIVE_FILENAME_SUFFIX" \
            --body "$ARCHIVE_FILENAME";
        then
            echo "Bucket name: $bucket"
            echo "Bucket key: $ENVIRONMENT/$ARCHIVE_FILENAME_SUFFIX"
            echo "Backup created successfully."

            put_metric_data "Backups" "success" "$bucket"
        else
            echo "Error uploading backup to S3";
            put_metric_data "Backups" "failure" "$bucket"
            exit 1;
        fi
    done
}

configure_container_role(){
    aws configure set default.region ${AWS_REGION:-eu-west-2}
}

run_api(){
    cd "$DIR_API";
    export SERVICE=api && . $VENV_API/bin/activate && exec flask run -p 6011 --host=0.0.0.0;
}

run_worker(){
    cd $DIR_API;
    export SERVICE=api_worker && . $VENV_API/bin/activate && exec dramatiq --processes 1 --threads 1 app.dramatiq:broker
}

run_periodiq(){
    cd $DIR_API;
    # We can't use the Periodiq CLI as then the import order is wrong for OpenTelemetry
    # (our instrumentation can't override the __main__ module)
    export SERVICE=api_periodiq && . $VENV_API/bin/activate && exec python -m app.periodiq -v app.dramatiq:broker
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do echo 'Debug mode active..'; sleep 30; done
else
    configure_container_role

    echo "Provided SERVICE_ACTION: $SERVICE_ACTION"

    if [[ $SERVICE_ACTION == "run_api" ]]; then
        run_api
    elif [[ $SERVICE_ACTION == "run_worker" ]]; then
        run_worker
    elif [[ $SERVICE_ACTION == "run_periodiq" ]]; then
        run_periodiq
    elif [[ $SERVICE_ACTION == "run_migrations" ]]; then

        if [[ ! -z $MASTER_USERNAME ]] && [[ ! -z $MASTER_PASSWORD ]]; then
            run_db_migrations
        else
            echo "Master credentials are required to use the service."
            exit 1;
        fi

    elif [[ $SERVICE_ACTION == "backup_database" ]]; then

        if [[ ! -z $MASTER_USERNAME ]] && [[ ! -z $MASTER_PASSWORD ]]; then
            run_backup_database
        else
            echo "Master credentials are required to use the service."
            put_metric_data "Backups" "failure"
            exit 1;
        fi

    else
        echo "Service action is not valid."
        exit 1;
    fi
fi
