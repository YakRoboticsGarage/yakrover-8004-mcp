#!/usr/bin/env bash

set -e

TOKEN=$1

if [[ -z "$TOKEN" ]]
then
  echo "Please provide an MCP server token"
  exit 1
fi

OPENCODE_CONF=${2:-$HOME/.config/opencode/opencode.json}

if [[ ! -f $OPENCODE_CONF ]]
then
  echo "Error in accessing the OpenCode configuration file at $OPENCODE_CONF"
  exit 2
else
  if [[ "null" = "$(jq '.mcp.yrg_fleet' $OPENCODE_CONF)" ]]
  then
    cp $OPENCODE_CONF $OPENCODE_CONF.original
    jq ".mcp.yrg_fleet = {type: \"remote\", url: \"https://mikel-pluckless-correctively.ngrok-free.dev/fleet/mcp\", enabled: true, headers: {Authorization: \"$TOKEN\"}}" $OPENCODE_CONF.original > $OPENCODE_CONF
  else
    echo "Already set in $OPENCODE_CONF. If you have problem, please check the content of the file"
  fi
fi

echo Your full OpenCode configuration:
cat $OPENCODE_CONF | jq

echo Original configuration available at: $OPENCODE_CONF.original

echo Done
