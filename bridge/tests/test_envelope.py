import unittest

from bridge.core.envelope import Envelope


class TestEnvelopeValidation(unittest.TestCase):
    def test_invalid_gtid_raises(self):
        with self.assertRaises(ValueError):
            Envelope(
                gtid="invalid",
                schema_version="1.0",
                from_agent="a",
                to_agent="b",
                payload={},
            )

    def test_missing_from_agent_raises(self):
        with self.assertRaises(ValueError):
            Envelope(
                gtid="cb:1:bridge-1:local",
                schema_version="1.0",
                from_agent="",
                to_agent="b",
                payload={},
            )

    def test_missing_to_agent_raises(self):
        with self.assertRaises(ValueError):
            Envelope(
                gtid="cb:1:bridge-1:local",
                schema_version="1.0",
                from_agent="a",
                to_agent="",
                payload={},
            )

    def test_payload_must_be_dict(self):
        with self.assertRaises(TypeError):
            Envelope(
                gtid="cb:1:bridge-1:local",
                schema_version="1.0",
                from_agent="a",
                to_agent="b",
                payload="not-a-dict",
            )


if __name__ == "__main__":
    unittest.main()
