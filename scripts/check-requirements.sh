#!/bin/sh

STAGED_FILES=$(git diff-index --name-only --cached --diff-filter=ACMR HEAD -- )
STAGED_REQ_FILES=0

if [ "$STAGED_FILES" = "" ]; then
    exit 0
fi

for FILE in $STAGED_FILES
do
    if [ "$FILE" = "requirements.in" ]; then
        STAGED_REQ_FILES=$((STAGED_REQ_FILES+1))
    elif [ "$FILE" = "requirements.txt" ]; then
        STAGED_REQ_FILES=$((STAGED_REQ_FILES+1))
    fi
done

if [ "$STAGED_REQ_FILES" -eq 1 ]; then
    printf "\e[37;41mChanges to requirements.in should be compiled to requirements.txt by running 'make freeze-requirements'. The file requirements.txt file should not be edited manually.\e[0m\n"
    exit 1
fi
exit 0
