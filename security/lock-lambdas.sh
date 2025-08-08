#!/bin/bash

lambdas=("ee-1-proxy" "ee-2-proxy" \
         "o2-1-proxy" "o2-2-proxy" \
         "three-1-proxy" "three-2-proxy" \
         "vodafone-1-proxy" "vodafone-2-proxy")

for lambda in "${lambdas[@]}"; do
    echo -ne "\rRemoving AllowInvocationFromECSApplication permission from $lambda..."
    aws lambda remove-permission \
        --function-name "$lambda" \
        --statement-id AllowInvocationFromECSApplication
    echo "done"
done

user_arn=$(aws sts get-caller-identity --query "Arn" \
  --output text | awk -F'[:/]' '{print "arn:aws:iam::" $5 ":role/" $7}')

for lambda in "${lambdas[@]}"; do
    echo -ne "\rAdding AllowInvocationFromECSApplication permission to $lambda for user $user_arn..."
    aws lambda add-permission \
        --function-name "$lambda" \
        --statement-id AllowInvocationFromECSApplication \
        --action lambda:InvokeFunction \
        --principal "$user_arn" \
        --region eu-west-2 > /dev/null
    echo "done"
done
