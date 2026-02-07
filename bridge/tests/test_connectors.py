import unittest

from bridge.connectors.base import Connector
from bridge.connectors.readonly_mux import ReadOnlyMux


class DummyConnector(Connector):
    def __init__(self, data):
        self._data = data

    def read(self):
        return list(self._data)


class TestConnectors(unittest.TestCase):
    def test_readonly_mux_reads_all(self):
        mux = ReadOnlyMux([DummyConnector([1]), DummyConnector([2, 3])])
        self.assertEqual(mux.read_all(), [1, 2, 3])

    def test_write_is_blocked(self):
        c = DummyConnector([1])
        with self.assertRaises(RuntimeError):
            c.write("x")

    def test_mux_rejects_non_readonly(self):
        class NotReadOnly:
            readonly = False

            def read(self):
                return []

        with self.assertRaises(RuntimeError):
            ReadOnlyMux([NotReadOnly()])


if __name__ == "__main__":
    unittest.main()
