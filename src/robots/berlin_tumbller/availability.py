"""Per-capability availability map, read from a JSON file on every call.

Lets an operator flip a capability offline for maintenance without
redeploying the server — edit the JSON, next bid picks it up.

Capability keys mirror the sensor / function vocabulary:
    movement, temperature, humidity, visual

The task category → capability mapping is defined in
`TASK_CATEGORY_CAPABILITIES` below.
"""

import json
import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "availability.json"

# Which capability does each marketplace task category require?
TASK_CATEGORY_CAPABILITIES = {
    "delivery_ground": "movement",
    "mapping": "movement",
    "env_sensing": "temperature",  # also humidity, handled separately
    "sensor_reading": "temperature",
    "visual_inspection": "visual",
}


def _path() -> Path:
    override = os.getenv("BERLIN_TUMBLLER_AVAILABILITY_PATH")
    return Path(override) if override else DEFAULT_PATH


def load() -> dict:
    """Read the availability map. Missing file / parse error → everything offline."""
    path = _path()
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def is_available(capability: str, availability_map: dict | None = None) -> tuple[bool, str | None]:
    """Return (available, reason). reason is None when available."""
    m = availability_map if availability_map is not None else load()
    entry = m.get(capability)
    if entry is None:
        return False, f"capability '{capability}' not declared"
    if not entry.get("available", False):
        return False, entry.get("reason") or "not available at this moment"
    return True, None


def capability_for_task_category(task_category: str) -> str | None:
    """Look up the capability a task category needs. None means unknown category."""
    return TASK_CATEGORY_CAPABILITIES.get(task_category)
