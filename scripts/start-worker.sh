#! /bin/sh

echo "Start script executing for API worker"

function configure_container_role(){
  aws configure set default.region ${AWS_REGION:-eu-west-2}
}

function run_worker(){
  echo "$(date +%s)" > "/eas/emergency-alerts-api/worker-beat-healthcheck"
  cd $DIR_API;
  . $VENV_API/bin/activate && . environment.sh && opentelemetry-instrument flask worker
}

if [[ ! -z $DEBUG ]]; then
    echo "Starting in debug mode.."
    while true; do echo 'Debug mode active..'; sleep 30; done
else
  configure_container_role
  run_worker
fi
