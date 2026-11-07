import unittest
from solution import format_duration

class DurationTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(format_duration(3661), "01:01:01")
    def test_zero(self):
        self.assertEqual(format_duration(0), "00:00:00")
    def test_over_day(self):
        self.assertEqual(format_duration(90061), "25:01:01")

if __name__ == "__main__":
    unittest.main(verbosity=2)
