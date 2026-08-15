from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import settings

settings.register_profile(
    "engineering",
    deadline=None,
    derandomize=True,
    max_examples=100,
    print_blob=True,
)
settings.load_profile("engineering")

REPOSITORY_ROOT = Path(__file__).parents[1]
EXAMPLE_SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "uma-fr1-foundation.yaml"
TRAFFIC_SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "traffic-queue-smoke.yaml"


@pytest.fixture
def scenario_data() -> dict[str, Any]:
    loaded = yaml.safe_load(EXAMPLE_SCENARIO.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return copy.deepcopy(loaded)


@pytest.fixture
def scheduler_scenario_data(scenario_data: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(scenario_data)
    data["scenario_id"] = "scheduler-qos-smoke"
    data["description"] = "Small aligned two-UE scenario for scheduler and KPI verification"
    data["simulation"] = {
        "warmup": {"value": 1, "unit": "ms"},
        "measurement": {"value": 4, "unit": "ms"},
        "drain": {"value": 1, "unit": "ms"},
    }
    data["models"].update(
        {"los_state": "explicit", "shadowing": "off", "interference": "noise_limited-v1"}
    )
    group = data["topology"]["ue_groups"]["users"]
    group["count"] = 2
    group["explicit_link_states"] = {"cell-a": ["los", "los"]}
    group["placement"] = {
        "mode": "explicit",
        "positions": [
            {
                "x": {"value": 100, "unit": "m"},
                "y": {"value": 0, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            },
            {
                "x": {"value": 400, "unit": "m"},
                "y": {"value": 0, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            },
        ],
        "minimum_2d_distance": {"value": 10, "unit": "m"},
    }
    data["traffic_profiles"]["broadband"] = {
        "source": {
            "type": "periodic",
            "interval": {"value": 0.5, "unit": "ms"},
            "initial_offset": {"value": 0, "unit": "ms"},
        },
        "packet_size": {"type": "constant", "payload": {"value": 250, "unit": "kbit"}},
        "queue": {"max_packets": 100},
        "deadline": None,
    }
    data["scheduler"] = {
        "policy": "proportional-fair",
        "parameters": {
            "averaging_alpha": 0.5,
            "initial_rate_floor": {"value": 1, "unit": "kbit/s"},
        },
    }
    return data
