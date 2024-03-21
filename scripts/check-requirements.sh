#!/bin/sh

STAGED_REQ_FILES=0

for FILE in "$@"
do
    if [ "$FILE" = "requirements.in" ]; then
        STAGED_REQ_FILES=$((STAGED_REQ_FILES+1))
    elif [ "$FILE" = "requirements.txt" ]; then
        STAGED_REQ_FILES=$((STAGED_REQ_FILES+1))
    fi
done

if [ "$STAGED_REQ_FILES" -eq 1 ]; then
    printf "\e[37;41mChanges to requirements.in should be compiled to requirements.txt by running 'make freeze-requirements'. The requirements.txt file should not be edited manually.\e[0m\n"
    exit 1
fi
exit 0
