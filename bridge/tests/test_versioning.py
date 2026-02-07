import unittest

from bridge.core.versioning import negotiate


class TestVersioning(unittest.TestCase):
    def test_negotiate_supported(self):
        self.assertTrue(negotiate("1.0"))

    def test_negotiate_unsupported(self):
        self.assertFalse(negotiate("9.9"))


if __name__ == "__main__":
    unittest.main()
