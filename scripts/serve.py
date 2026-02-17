"""
Start the MCP gateway for one or more robot plugins.

Usage:
    # Serve all discovered robot plugins
    PYTHONPATH=src uv run python scripts/serve.py

    # Serve only specific robots
    PYTHONPATH=src uv run python scripts/serve.py --robots fakerover

    # Custom port
    PYTHONPATH=src uv run python scripts/serve.py --robots fakerover --port 8001

Endpoints created:
    /{robot}/mcp   — Per-robot MCP server
    /              — Gateway info (lists all mounted robots)
"""

import argparse
import sys
import os

# Ensure src/ is on the path when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import uvicorn

from robots import discover_plugins
from core.server import create_gateway

parser = argparse.ArgumentParser(description="Start the robot fleet MCP gateway")
parser.add_argument("--robots", nargs="*", help="Robot plugins to load (default: all)")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()

# Discover and filter plugins
all_plugins = discover_plugins()
if args.robots:
    unknown = set(args.robots) - set(all_plugins.keys())
    if unknown:
        print(f"Unknown robot(s): {unknown}. Available: {list(all_plugins.keys())}")
        sys.exit(1)
    selected = {k: v for k, v in all_plugins.items() if k in args.robots}
else:
    selected = all_plugins

if not selected:
    print("No robot plugins found. Check src/robots/ for plugin packages.")
    sys.exit(1)

plugins = {name: cls() for name, cls in selected.items()}

print(f"Loading {len(plugins)} robot(s): {', '.join(plugins.keys())}")
for name, plugin in plugins.items():
    meta = plugin.metadata()
    print(f"  /{name}/mcp — {meta.name} ({len(plugin.tool_names())} tools)")

app = create_gateway(plugins)

try:
    uvicorn.run(app, host="0.0.0.0", port=args.port)
except KeyboardInterrupt:
    print("\nShutting down.")
