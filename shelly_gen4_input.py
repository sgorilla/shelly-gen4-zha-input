"""Expose a Shelly Gen4 physical input independently of its relay in ZHA.

For ZHA 2.4.3 / zha-quirks 2.4.1. See README.md before installing.
ZHA already handles incoming OnOff client commands. Do not add another
command listener: doing so could apply toggle commands twice.
"""

from zigpy.zcl import ClusterType
from zigpy.zcl.clusters.general import OnOff, OnOffConfiguration, Scenes

from zhaquirks.builder import EntityType, QuirkBuilder
from zhaquirks.shelly.wifi import (
    SHELLY_WIFI_SETUP_CLUSTER_ID,
    SHELLY_WIFI_SETUP_ENDPOINT_ID,
    SHELLY_WIFI_SETUP_PROFILE_ID,
    ShellyCustomProfileDevice,
    ShellyWiFiSetupCluster,
)

SUPPORTED_MODELS = ("1", "1PM", "Mini1", "Mini1PM")

# Optional recovery for a stale interview. Leave empty unless endpoint 2 has
# independently been verified on the physical device. Keys are lowercase,
# colon-separated Zigbee IEEE addresses; values are exact Zigbee model names.
# This is deliberately NOT enabled for every device missing endpoint 2.
VERIFIED_MISSING_INPUT_ENDPOINTS: dict[str, str] = {}


def has_expected_base(device):
    """Require a relay and the stock Shelly management endpoint."""
    relay = device.endpoints.get(1)
    management = device.endpoints.get(SHELLY_WIFI_SETUP_ENDPOINT_ID)
    return (
        relay is not None
        and relay.profile_id == 0x0104
        and OnOff.cluster_id in relay.in_clusters
        and management is not None
        and management.profile_id == SHELLY_WIFI_SETUP_PROFILE_ID
        and SHELLY_WIFI_SETUP_CLUSTER_ID in management.in_clusters
    )


def has_input_endpoint(device):
    """Accept only an interviewed input endpoint with the expected clusters."""
    endpoint = device.endpoints.get(2)
    return (
        endpoint is not None
        and endpoint.profile_id == 0x0104
        and OnOffConfiguration.cluster_id in endpoint.in_clusters
        and OnOff.cluster_id in endpoint.out_clusters
    )


def has_verified_missing_input(device):
    """Restore a missing endpoint only for an explicitly verified device."""
    return (
        2 not in device.endpoints
        and VERIFIED_MISSING_INPUT_ENDPOINTS.get(str(device.ieee)) == device.model
    )


def input_builder(model):
    """Preserve stock management support and describe the input entity."""
    return (
        QuirkBuilder("Shelly", model)
        .filter(has_expected_base)
        .device_class(ShellyCustomProfileDevice)
        .replaces(ShellyWiFiSetupCluster, endpoint_id=SHELLY_WIFI_SETUP_ENDPOINT_ID)
        .binary_sensor(
            attribute_name=OnOff.AttributeDefs.on_off.name,
            cluster_id=OnOff.cluster_id,
            endpoint_id=2,
            cluster_type=ClusterType.Client,
            entity_type=EntityType.STANDARD,
            translation_key="input",
            fallback_name="Input",
        )
    )


for model in SUPPORTED_MODELS:
    input_builder(model).filter(has_input_endpoint).add_to_registry()
    (
        input_builder(model)
        .filter(has_verified_missing_input)
        .adds_endpoint(2, profile_id=0x0104, device_type=0x0000)
        .adds(OnOffConfiguration, endpoint_id=2)
        .adds(OnOff, endpoint_id=2, cluster_type=ClusterType.Client)
        .adds(Scenes, endpoint_id=2, cluster_type=ClusterType.Client)
        .add_to_registry()
    )
