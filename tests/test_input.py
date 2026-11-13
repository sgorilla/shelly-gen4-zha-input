"""Offline regression tests: synthetic devices, no coordinator or HA access."""

import unittest
from unittest.mock import MagicMock

import zigpy.types as t
from zigpy.device import Device
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import OnOff
from zigpy.zdo.types import NodeDescriptor
import zhaquirks

zhaquirks.setup()

import shelly_gen4_input as quirk  # noqa: E402
from zha.quirks import DEVICE_REGISTRY  # noqa: E402
from zha.application.platforms.binary_sensor import BinarySensor  # noqa: E402
from zha.application.platforms.virtual import OnOffClientCacheSync  # noqa: E402

IEEE = "00:11:22:33:44:55:66:77"


def device_fixture(model="1", *, with_input=True, manufacturer="Shelly", ieee=IEEE):
    device = Device(MagicMock(), t.EUI64.convert(ieee), 0x1234)
    device.manufacturer = manufacturer
    device.model = model
    device.node_desc = NodeDescriptor(
        logical_type=1, complex_descriptor_available=0,
        user_descriptor_available=0, reserved=0, aps_flags=0,
        frequency_band=8, mac_capability_flags=0x8E,
        manufacturer_code=0x1490, maximum_buffer_size=82,
        maximum_incoming_transfer_size=82, server_mask=11264,
        maximum_outgoing_transfer_size=82, descriptor_capability_field=0,
    )
    relay = device.add_endpoint(1)
    relay.profile_id, relay.device_type = 0x0104, 0x0100
    for cluster_id in (0, 3, 4, 5, 6):
        relay.add_input_cluster(cluster_id)
    relay.in_clusters[6].update_attribute(0, True)
    management = device.add_endpoint(239)
    management.profile_id, management.device_type = 0xC001, 0
    management.add_input_cluster(0xFC02)
    if with_input:
        endpoint = device.add_endpoint(2)
        endpoint.profile_id, endpoint.device_type = 0x0104, 0
        endpoint.add_input_cluster(7)
        endpoint.add_output_cluster(6)
        endpoint.add_output_cluster(5)
    return device


def matches(device):
    entry = DEVICE_REGISTRY.match_entry(device)
    return entry is not None and entry.source.module == quirk.__name__


def resolve_entities(device):
    entry = DEVICE_REGISTRY.match_entry(device)
    resolved = DEVICE_REGISTRY.resolve(device)
    gateway = MagicMock()
    gateway.state.node_info.ieee = t.EUI64.convert("00:11:22:33:44:55:66:88")
    gateway.config.config_overrides = {}
    zha_device = entry.zha_device_factory(resolved, gateway)
    entities = list(zha_device.discover_entities())
    return resolved, entities


class InputTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        quirk.VERIFIED_MISSING_INPUT_ENDPOINTS.clear()

    def test_model_and_signature_guards(self):
        for model in quirk.SUPPORTED_MODELS:
            with self.subTest(model=model):
                self.assertTrue(matches(device_fixture(model)))
        for model in ("2PM", "EM Mini", "unknown"):
            self.assertFalse(matches(device_fixture(model)))
        self.assertFalse(matches(device_fixture(manufacturer="Other")))
        self.assertFalse(matches(device_fixture(with_input=False)))
        wrong = device_fixture()
        wrong.endpoints[2].out_clusters.pop(6)
        wrong.endpoints[2].add_input_cluster(6)
        self.assertFalse(matches(wrong))
        wrong = device_fixture()
        wrong.endpoints[239].profile_id = 0x0104
        self.assertFalse(matches(wrong))

    def test_verified_missing_endpoint_is_per_device_and_model(self):
        original = device_fixture(with_input=False)
        self.assertFalse(matches(original))
        quirk.VERIFIED_MISSING_INPUT_ENDPOINTS[IEEE] = "Mini1PM"
        self.assertFalse(matches(original))
        quirk.VERIFIED_MISSING_INPUT_ENDPOINTS[IEEE] = "1"
        self.assertTrue(matches(original))
        resolved, entities = resolve_entities(original)
        self.assertNotIn(2, original.endpoints)
        self.assertIn(6, resolved.endpoints[2].out_clusters)
        self.assertEqual(1, sum(isinstance(e, BinarySensor) for e in entities))
        other = device_fixture(with_input=False, ieee="00:11:22:33:44:55:66:99")
        self.assertFalse(matches(other))

    async def test_commands_change_input_once_and_leave_relay_alone(self):
        for model in quirk.SUPPORTED_MODELS:
            with self.subTest(model=model):
                original = device_fixture(model)
                resolved, entities = resolve_entities(original)
                sensors = [e for e in entities if isinstance(e, BinarySensor)]
                mirrors = [e for e in entities if isinstance(e, OnOffClientCacheSync)]
                self.assertEqual(1, len(sensors))
                self.assertEqual(1, len(mirrors))
                sensor, mirror = sensors[0], mirrors[0]
                client = resolved.endpoints[2].out_clusters[6]
                self.assertIs(sensor._cluster, client)
                self.assertIs(mirror._cluster, client)
                self.assertIsInstance(
                    resolved.endpoints[239].in_clusters[0xFC02],
                    quirk.ShellyWiFiSetupCluster,
                )
                self.assertIsNone(client.get("on_off"))
                sensor.on_add()
                mirror.on_add()
                try:
                    for tsn, (command_id, expected) in enumerate(
                        [(0, False), (1, True), (2, False), (2, True), (0, False)]
                    ):
                        header = foundation.ZCLHeader.cluster(
                            tsn=tsn, command_id=command_id,
                            direction=foundation.Direction.Client_to_Server,
                        )
                        header = header.replace(frame_control=header.frame_control.replace(
                            disable_default_response=True
                        ))
                        command = OnOff.server_commands[command_id].schema()
                        client.handle_message(header, command)
                        self.assertEqual(expected, sensor.is_on)
                        self.assertTrue(resolved.endpoints[1].in_clusters[6].get("on_off"))
                        self.assertIsNone(original.endpoints[2].out_clusters[6].get("on_off"))
                finally:
                    await sensor.on_remove()
                    await mirror.on_remove()


if __name__ == "__main__":
    unittest.main()
