from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ports", ROOT / "scripts/ports.py")
PORTS_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = PORTS_MODULE
SPEC.loader.exec_module(PORTS_MODULE)
ACCEPTANCE_SPEC = importlib.util.spec_from_file_location("acceptance", ROOT / "scripts/acceptance.py")
ACCEPTANCE_MODULE = importlib.util.module_from_spec(ACCEPTANCE_SPEC)
assert ACCEPTANCE_SPEC and ACCEPTANCE_SPEC.loader
sys.modules[ACCEPTANCE_SPEC.name] = ACCEPTANCE_MODULE
ACCEPTANCE_SPEC.loader.exec_module(ACCEPTANCE_MODULE)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ports = PORTS_MODULE.load_ports()

    def test_catalog_has_exactly_fifty_packages(self) -> None:
        PORTS_MODULE.validate_catalog(self.ports)
        self.assertEqual(sum(port.user_visible for port in self.ports.values()), 50)

    def test_batches_cover_catalog_exactly_once(self) -> None:
        batches = PORTS_MODULE.load_batches(self.ports)
        flattened = [package for packages in batches.values() for package in packages]
        self.assertEqual(len(flattened), 50)
        self.assertEqual(set(flattened), {name for name, port in self.ports.items() if port.user_visible})

    def test_every_source_is_pinned(self) -> None:
        for port in self.ports.values():
            self.assertRegex(port.source_sha256, r"^[a-f0-9]{64}$")
            self.assertTrue(port.source_url.startswith("https://"))

    def test_build_dependencies_are_known_and_acyclic(self) -> None:
        PORTS_MODULE.validate_catalog(self.ports)
        for port in self.ports.values():
            for dependency in port.data["build"].get("dependencies", []):
                self.assertIn(dependency, self.ports)

    def test_network_packages_are_not_full(self) -> None:
        for name in ("curl", "wget"):
            self.assertEqual(self.ports[name].data["runtime"]["capability"], "http")
        for name in ("openssh-client", "rsync", "dnsutils", "netcat-openbsd", "openssl"):
            self.assertEqual(self.ports[name].data["runtime"]["capability"], "socket-preview")

    def test_stable_requires_every_acceptance_check(self) -> None:
        data = {"checks": {name: {"passed": True} for name in ACCEPTANCE_MODULE.CHECKS}}
        self.assertTrue(ACCEPTANCE_MODULE.is_stable(data))
        data["checks"]["chrome"] = {"passed": False}
        self.assertFalse(ACCEPTANCE_MODULE.is_stable(data))

    def test_stage_rejects_native_or_missing_commands(self) -> None:
        port = self.ports["grep"]
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            binary = stage / "usr/local/bin/grep"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"native")
            with self.assertRaises(PORTS_MODULE.PortError):
                PORTS_MODULE.validate_stage(port, stage)


if __name__ == "__main__":
    unittest.main()
