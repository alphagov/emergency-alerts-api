#! /bin/bash

if [ $1 == "" ]; then
  echo "Metric name is a required field."
  exit 1
fi

if [ $2 == "" ]; then
  echo "Start time is required."
  exit 1
fi

if [ $3 == "" ]; then
  echo "End time is required."
  exit 1
fi

RESOURCE_PREFIX="$4"

aws cloudwatch get-metric-data --start-time $2 --end-time $3 --metric-data-queries '[
  {
    "Id": "migrationResults",
    "MetricStat": {
      "Metric": {
        "Namespace": "ECS/ContainerInsights",
        "MetricName": "'$1'",
        "Dimensions": [
          {
            "Name": "ClusterName",
            "Value": "${RESOURCE_PREFIX}-cluster"
          },
          {
            "Name": "ServiceName",
            "Value": "${RESOURCE_PREFIX}-migrations"
          },
          {
            "Name": "Version",
            "Value": "$MIGRATION_VERSION"
          }
        ]
      },
      "Period": 60,
      "Stat": "Sum",
      "Unit": "Count"
    },
    "ReturnData": true
  }
]' | jq '.MetricDataResults[0].Values | add'
