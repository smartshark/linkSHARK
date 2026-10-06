#!/bin/sh
PLUGIN_PATH=$1

COMMAND="python3 $1/main.py --db-database $4 --db-hostname $5 --db-port $6 
--project-name ${10}"

if [ ! -z ${2} ] && [ ${2} != "None" ]; then
	COMMAND="$COMMAND --db-user ${2}"
fi

if [ ! -z ${3} ] && [ ${3} != "None" ]; then
	COMMAND="$COMMAND --db-password ${3}"
fi

if [ ! -z ${7} ] && [ ${7} != "None" ]; then
	COMMAND="$COMMAND --db-authentication ${7}"
fi

if [ ! -z ${8} ] && [ ${8} != "None" ]; then
    COMMAND="$COMMAND --ssl"
fi

if [ ! -z ${9} ] && [ ${9} != "None" ]; then
    COMMAND="$COMMAND --log-level ${9}"
fi

if [ ! -z ${11} ] && [ ${11} != "None" ]; then
    COMMAND="$COMMAND --broken-keys ${11}"
fi

if [ ! -z ${12} ] && [ ${12} != "None" ]; then
    COMMAND="$COMMAND --correct-key ${12}"
fi

$COMMAND
