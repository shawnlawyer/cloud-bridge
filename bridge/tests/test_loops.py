import unittest

from bridge.core.envelope import Envelope
from bridge.core.routing import MAX_HOPS


class TestLoops(unittest.TestCase):
    def test_hop_limit_exceeded_raises(self):
        env = Envelope(
            gtid="cb:1:bridge-1:local",
            schema_version="1.0",
            from_agent="a",
            to_agent="b",
            payload={},
            hop_count=8,
        )
        with self.assertRaises(RuntimeError):
            env.increment_hop(max_hops=8)

    def test_increment_reaches_cap(self):
        env = Envelope(
            gtid="cb:1:bridge-1:local",
            schema_version="1.0",
            from_agent="a",
            to_agent="b",
            payload={},
            hop_count=0,
        )
        for _ in range(MAX_HOPS):
            env = env.increment_hop(max_hops=MAX_HOPS)
        with self.assertRaises(RuntimeError):
            env.increment_hop(max_hops=MAX_HOPS)


if __name__ == "__main__":
    unittest.main()
