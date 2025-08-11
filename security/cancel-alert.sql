-- IDENTIFY ALERT BY CONTENT AND SET 'exclude' FLAG TO TRUE
DO $$
DECLARE
	-- string that uniquely identifies alert
	search_content text := 'PLACEHOLDER';
	alert_id uuid;
	alert_content text;
	alert_created_by uuid;
	alert_approved_by uuid;
	alert_created_by_api_key uuid;
BEGIN
	SELECT id, content, created_by_id, approved_by_id, created_by_api_key_id
	INTO alert_id, alert_content, alert_created_by, alert_approved_by, alert_created_by_api_key
	FROM broadcast_message
	WHERE status = 'broadcasting'
	  AND content LIKE '%' || search_content || '%';
	IF alert_id IS NULL THEN
		RAISE NOTICE 'No matching alert found.';
	ELSE
		RAISE NOTICE 'Alert ID: %', alert_id;
		RAISE NOTICE 'Alert Content: %', alert_content;
		RAISE NOTICE 'Created By: %', alert_created_by;
		RAISE NOTICE 'Approved By: %', alert_approved_by;
		RAISE NOTICE 'Create By API Key: %', alert_created_by_api_key;
	END IF;

	-- EXCLUDE MESSAGE FROM GOV.UK/ALERTS PAGE
	UPDATE broadcast_message
	SET exclude = true
	WHERE id = alert_id;

	-- BLOCK COMPROMISED USER ACCOUNTS
	IF alert_created_by IS NOT NULL THEN
		UPDATE users SET state = 'blocked' WHERE id = alert_created_by;
		DELETE FROM user_to_service WHERE user_id = alert_created_by;
		DELETE FROM user_to_organisation WHERE user_id = alert_created_by;
		DELETE FROM user_folder_permissions WHERE user_id = alert_created_by;
		DELETE FROM permissions WHERE user_id = alert_created_by;
	END IF;

	IF alert_approved_by IS DISTINCT FROM alert_created_by THEN
		UPDATE users SET state = 'blocked' WHERE id = alert_approved_by;
		DELETE FROM user_to_service WHERE user_id = alert_approved_by;
		DELETE FROM user_to_organisation WHERE user_id = alert_approved_by;
		DELETE FROM user_folder_permissions WHERE user_id = alert_approved_by;
		DELETE FROM permissions WHERE user_id = alert_approved_by;
	END IF;

	-- BLOCK COMPROMOSED API KEYS
	IF alert_created_by_api_key IS NOT NULL THEN
		UPDATE api_keys
		SET expiry_date = NOW(),
			updated_at = NOW(),
			version = version + 1
		WHERE id = alert_created_by_api_key;

		INSERT INTO api_keys_history (
		    id,
		    name,
		    secret,
		    service_id,
		    expiry_date,
		    created_at,
		    created_by_id,
		    updated_at,
		    version,
		    key_type
		)
		SELECT * FROM api_keys
		WHERE id = alert_created_by_api_key;
	END IF;
END
$$;

-- EXTRACT BROADCAST MESSAGE DATA AND CONSTRUCT LAMBDA PAYLOADS
DO $$
DECLARE
	msg RECORD;
BEGIN
	FOR msg IN
		SELECT bpm.provider as mno,
		    bpm.id as id,
		    LPAD(TO_HEX(bpmn.broadcast_provider_message_number), 8, '0') as number,
		    TO_CHAR(bpm.created_at, 'YYYY-MM-DD"T"HH24:MI:SS.US') || 'Z' as created_at,
			TO_CHAR(be.sent_at, 'YYYY-MM-DD"T"HH24:MI:SS') || '-00:00' as sent_at
		FROM broadcast_message bm
		JOIN broadcast_event be ON be.broadcast_message_id = bm.id
		JOIN broadcast_provider_message bpm ON bpm.broadcast_event_id = be.id
		LEFT JOIN broadcast_provider_message_number bpmn ON bpmn.broadcast_provider_message_id = bpm.id
		WHERE bm.status = 'broadcasting' AND bm.exclude = true
	LOOP
		IF msg.mno = 'vodafone' THEN
			RAISE NOTICE $msg1$
TO CANCEL THE % ALERT, RUN THE FOLLOWING COMMAND IN A GDS CLI CELL-BROADCAST SHELL:

aws lambda invoke \
--function-name %-1-proxy \
--invocation-type Event \
--cli-binary-format raw-in-base64-out \
--payload "$(cat <<EOF
{
	"message_type": "cancel",
	"identifier": "%",
	"message_number": "%",
	"message_format": "ibag",
	"references": [
		{
			"message_id": "%",
			"message_number": "%",
			"sent": "%"
		}
	],
	"sent": "%",
	"cbc_target": "cbc_a"
}
EOF
)" \
/dev/null

			$msg1$, UPPER(msg.mno), msg.mno, msg.id, msg.number, msg.id, msg.number, msg.created_at, msg.sent_at;
		ELSE
			RAISE NOTICE $msg2$
TO CANCEL THE % ALERT, RUN THE FOLLOWING COMMAND IN A GDS CLI CELL-BROADCAST SHELL:

aws lambda invoke \
--function-name %-1-proxy \
--invocation-type Event \
--cli-binary-format raw-in-base64-out \
--payload "$(cat <<EOF
{
	"message_type": "cancel",
	"identifier": "%",
	"message_format": "cap",
	"references": [
		{
			"message_id": "%",
			"sent": "%"
		}
	],
	"sent": "%",
	"cbc_target": "cbc_a"
}
EOF
)" \
/dev/null

			$msg2$, UPPER(msg.mno), msg.mno, msg.id, msg.id, msg.created_at, msg.sent_at;
		END IF;
	END LOOP;
END
$$;

-- EMIT COMMANDS TO PURGE ALL SQS QUEUES
DO $$
DECLARE
	target_env text := 'production';
BEGIN

	RAISE NOTICE $msg1$
TO PURGE ALL SQS QUEUES, RUN THE FOLLOWING COMMAND IN A GDS CLI EMERGENCY-ALERTS SHELL:

aws sqs list-queues --queue-name-prefix % --output text --query 'QueueUrls[]' \
| xargs -n 1 aws sqs purge-queue --queue-url > /dev/null

	$msg1$, target_env;

END
$$;

-- EMIT COMMANDS TO RESTART ALL INSTANCES WITH CELERY WORKERS
DO $$
DECLARE
	target_cluster text := 'eas-app-cluster';
	service_prefix text := 'eas-app';
BEGIN

	RAISE NOTICE $msg1$
TO RESTART THE CELERY ECS INSTANCE, RUN THE FOLLOWING COMMAND IN A GDS CLI EMERGENCY-ALERTS SHELL:

aws ecs list-tasks \
    --cluster % \
    --service-name %-celery \
    --query 'taskArns[]' \
    --output text \
| xargs -n 1 aws ecs stop-task --cluster % --task > dev/null

	$msg1$, target_cluster, service_prefix, target_cluster;


	RAISE NOTICE $msg2$
TO RESTART THE GOVUK-ALERTS INSTANCE, RUN THE FOLLOWING COMMAND IN A GDS CLI EMERGENCY-ALERTS SHELL:

aws ecs list-tasks \
    --cluster % \
    --service-name %-govuk-alerts \
    --query 'taskArns[]' \
    --output text \
| xargs -n 1 aws ecs stop-task --cluster % --task > dev/null

	$msg2$, target_cluster, service_prefix, target_cluster;


	RAISE NOTICE $msg3$
TO RESTART THE API INSTANCES, RUN THE FOLLOWING COMMAND IN A GDS CLI EMERGENCY-ALERTS SHELL:

for task in $(aws ecs list-tasks --cluster % --service-name %-api --query 'taskArns[]' --output text); do
    aws ecs stop-task --cluster % --task $task > dev/null
done

	$msg3$, target_cluster, service_prefix, target_cluster;

END
$$;
