from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
KEY_NAME = "CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY"


class FastApiComposeEnvironmentTests(unittest.TestCase):
    def compose_config(
        self,
        *,
        include_encryption_key: bool,
        services: tuple[str, ...] = ("fastapi",),
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("CONDUCTOR_")
        }
        if include_encryption_key:
            environment[KEY_NAME] = "compose-wiring-test-placeholder"

        return subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "config",
                "--no-env-resolution",
                "--format",
                "json",
                *services,
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_fastapi_requires_credentials_encryption_key(self):
        result = self.compose_config(include_encryption_key=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(KEY_NAME, result.stderr)

    def test_fastapi_receives_credentials_encryption_key(self):
        result = self.compose_config(include_encryption_key=True)

        self.assertEqual(result.returncode, 0)
        config = json.loads(result.stdout)
        self.assertIn(KEY_NAME, config["services"]["fastapi"]["environment"])

    def test_frontend_proxy_uses_an_exact_trusted_compose_hop(self):
        result = self.compose_config(
            include_encryption_key=True,
            services=("fastapi", "frontend"),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        trusted_cidrs = config["services"]["fastapi"]["environment"][
            "CONDUCTOR_TRUSTED_PROXY_CIDRS"
        ]
        self.assertEqual(
            trusted_cidrs,
            "127.0.0.0/8,::1/128,172.31.251.3/32",
        )
        for broad_cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
            self.assertNotIn(broad_cidr, trusted_cidrs)

        network = config["networks"]["frontend_backend"]
        self.assertEqual(network["ipam"]["config"], [{"subnet": "172.31.251.0/29"}])
        self.assertIn("frontend_backend", config["services"]["fastapi"]["networks"])
        self.assertEqual(
            config["services"]["frontend"]["networks"]["frontend_backend"][
                "ipv4_address"
            ],
            "172.31.251.3",
        )
        self.assertTrue(
            any(
                volume["type"] == "volume" and volume["target"] == "/app/node_modules"
                for volume in config["services"]["frontend"]["volumes"]
            ),
            "frontend container dependencies must not overwrite host node_modules",
        )


if __name__ == "__main__":
    unittest.main()
