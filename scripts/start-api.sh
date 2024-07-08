#! /bin/sh
echo "Start script executing for api.."

function put_metric_data(){
    if [[ $1 != "success" && $1 != "failure" ]]; then
        echo "Invalid status type (success || failure)."
        exit 1;
    fi

    aws cloudwatch put-metric-data \
        --namespace Backups \
        --dimensions Repository=emergency-alerts-api \
        --metric-name $SERVICE_ACTION \
        --dimensions Name=JobStatus,Value=$1 \
        --value 1 \
        --timestamp $(date -u +"%Y-%m-%dT%H:%M:%S.000Z") \
        --region eu-west-2
}

function run_db_migrations(){
    cd $DIR_API;
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

function backup_database(){
    if [[ -z $RDS_HOST  ]]; then
        echo "RDS_HOST is not provided and required."
        put_metric_data "failure"
        exit 1;
    fi

    if [[ -z $RDS_PORT  ]]; then
        echo "RDS_PORT is not provided and required."
        put_metric_data "failure"
        exit 1;
    fi

    if [[ -z $DATABASE  ]]; then
        echo "DATABASE name is not provided and required."
        put_metric_data "failure"
        exit 1;
    fi

    if [[ -z $BACKUP_BUCKET_NAME ]]; then
        echo "BACKUP_BUCKET_NAME is not provided and required."
        put_metric_data "failure"
        exit 1;
    fi

    if [[ -z $ENVIRONMENT ]]; then
        echo "ENVIRONMENT is not provided and required."
        put_metric_data "failure"
        exit 1;
    fi

    SQL_FILENAME=$ENVIRONMENT-$(date -u +"%Y-%m-%d-%H-%M-%S").sql
    rm -f $SQL_FILENAME

    # To exclude table use: --exclude-table TABLE_NAME
    PGPASSWORD=$MASTER_PASSWORD pg_dump -h $RDS_HOST -p $RDS_PORT -U $MASTER_USERNAME \
        --file $SQL_FILENAME \
        $DATABASE

    if [ $(cat $SQL_FILENAME | grep "PostgreSQL database dump" | wc -l) -lt 2 ]; then
        echo "There was an issue creating the backup.";
        put_metric_data "failure"
        exit 1;
    fi

    ARCHIVE_FILENAME=$SQL_FILENAME.tar.gz
    tar -czf $ARCHIVE_FILENAME $SQL_FILENAME

    # Upload the backup to S3
    if aws s3api put-object \
        --bucket $BACKUP_BUCKET_NAME \
        --key $ENVIRONMENT/$ARCHIVE_FILENAME \
        --body $ARCHIVE_FILENAME;
    then
        echo "Bucket name: $BACKUP_BUCKET_NAME"
        echo "Bucket key: $ENVIRONMENT/$ARCHIVE_FILENAME"
        echo "Backup created successfully."

        put_metric_data "success"
    else
        echo "Error uploading backup to S3";
        put_metric_data "failure"
        exit 1;
    fi
}

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

    if [[ $SERVICE_ACTION == "run_api" ]]; then
        run_celery
        run_api

    elif [[ $SERVICE_ACTION == "run_migrations" ]]; then

        if [[ ! -z $MASTER_USERNAME ]] && [[ ! -z $MASTER_PASSWORD ]]; then
            run_db_migrations
        else
            echo "Master credentials are required to use the service."
            exit 1;
        fi

    elif [[ $SERVICE_ACTION == "backup_database" ]]; then

        if [[ ! -z $MASTER_USERNAME ]] && [[ ! -z $MASTER_PASSWORD ]]; then
            backup_database
        else
            echo "Master credentials are required to use the service."
            put_metric_data "failure"
            exit 1;
        fi

    else
        echo "Service action is not valid."
        exit 1;
    fi
fi
