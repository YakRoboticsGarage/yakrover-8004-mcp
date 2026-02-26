$ErrorActionPreference = 'Stop'

$TOKEN = $args[0]

if (-not $TOKEN) {
    Write-Host "Please provide an MCP server token"
    exit 1
}

$OPENCODE_CONF = if ($args[1]) { $args[1] } else { "$env:USERPROFILE\.config\opencode\opencode.json" }

if (-not (Test-Path $OPENCODE_CONF)) {
    Write-Host "Error in accessing the OpenCode configuration file at $OPENCODE_CONF"
    exit 2
} else {
    $fleetValue = jq '.mcp.yrg_fleet' $OPENCODE_CONF
    if ($fleetValue -eq "null") {
        Copy-Item $OPENCODE_CONF "$OPENCODE_CONF.original"
        jq ".mcp.yrg_fleet = {type: \"remote\", url: \"https://mikel-pluckless-correctively.ngrok-free.dev/fleet/mcp\", enabled: true, headers: {Authorization: \"$TOKEN\"}}" $OPENCODE_CONF.original > "$OPENCODE_CONF.fleet"
        jq ".mcp.yrg_tumbller = {type: \"remote\", url: \"https://mikel-pluckless-correctively.ngrok-free.dev/tumbller/mcp\", enabled: true, headers: {Authorization: \"$TOKEN\"}}" "$OPENCODE_CONF.fleet" > $OPENCODE_CONF
        Remove-Item "$OPENCODE_CONF.fleet"
    } else {
        Write-Host "Already set in $OPENCODE_CONF. If you have problem, please check the content of the file"
    }
}

Write-Host "Your full OpenCode configuration:"
cat $OPENCODE_CONF | jq

Write-Host "Original configuration available at: $OPENCODE_CONF.original"

Write-Host "Done"