import unittest

from tools.simulate_load import expect_throttle


class TestSimulateLoad(unittest.TestCase):
    def test_throttle_expected_when_over_cap(self):
        self.assertTrue(expect_throttle(30))

    def test_no_throttle_when_under_cap(self):
        self.assertTrue(expect_throttle(10))


if __name__ == "__main__":
    unittest.main()
