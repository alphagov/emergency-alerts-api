#! /bin/sh
timestamp_filename='/eas/emergency-alerts-api/celery-beat-healthcheck'
expected_update_interval=240
previous_timestamp=0
current_timestamp=$(date +%s)

function get_previous_timestamp(){
  # Get and validate the preview timestamp.
  previous_timestamp=$(<$timestamp_filename)

  if [[ -z $previous_timestamp ]] || [[ "$previous_timestamp" == "" ]]; then
    echo "Could not read previous timestamp file."
    exit 1
  fi
}

function compare_timestamps(){
  get_previous_timestamp

  adjusted_timestamp=$(( $current_timestamp - $expected_update_interval ))
  if [[ $adjusted_timestamp > $previous_timestamp ]]; then
    # As the file is older than allowed timeframe, fail healthcheck.
    last_updated_timestamp=$(date -r $previous_timestamp)
    echo "The file has not been updated within $expected_update_interval seconds."
    echo "Last updated at $last_updated_timestamp"
    exit 1
  fi
}

if [[ ! -z $DEBUG ]]; then
  echo "Debug mode active.."
else
  compare_timestamps
fi
