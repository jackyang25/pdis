"""Ask opens a cited source only at a public address, and the check holds at connect time."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from services.assistant import web_sources

URL = "http://source.example/paper"


def resolved(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))]


class PublicAddressTests(unittest.TestCase):
    def test_a_name_that_rebinds_to_a_private_address_is_never_connected(self) -> None:
        """The first lookup answers public, the one used to connect answers private."""
        answers = iter([resolved("93.184.216.34"), resolved("169.254.169.254")])
        with patch.object(
            web_sources.socket, "getaddrinfo", side_effect=lambda *a, **k: next(answers)
        ), patch.object(web_sources.socket, "create_connection") as connect:
            text = web_sources.fetch_source(URL, {URL})
        connect.assert_not_called()
        self.assertIn("Could not open this source", text)

    def test_the_connection_goes_to_the_address_that_was_checked(self) -> None:
        with patch.object(
            web_sources.socket, "getaddrinfo", return_value=resolved("93.184.216.34")
        ), patch.object(
            web_sources.socket, "create_connection", side_effect=ConnectionRefusedError
        ) as connect:
            web_sources.fetch_source(URL, {URL})
        self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 80))

    def test_an_environment_proxy_is_not_used(self) -> None:
        """Through a proxy the address connected to is the proxy's, which no check governs."""
        with patch.dict("os.environ", {"http_proxy": "http://10.0.0.1:3128"}), patch.object(
            web_sources.socket, "getaddrinfo", return_value=resolved("93.184.216.34")
        ), patch.object(
            web_sources.socket, "create_connection", side_effect=ConnectionRefusedError
        ) as connect:
            web_sources.fetch_source(URL, {URL})
        self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 80))


if __name__ == "__main__":
    unittest.main()
