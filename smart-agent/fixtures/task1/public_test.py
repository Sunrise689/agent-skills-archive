import unittest
from solution import clamp_int

class PublicClampTests(unittest.TestCase):
    def test_below_range(self):
        self.assertEqual(clamp_int(-5, 0, 10), 0)

    def test_above_range(self):
        self.assertEqual(clamp_int(15, 0, 10), 10)

    def test_inside_range(self):
        self.assertEqual(clamp_int(6, 0, 10), 6)

if __name__ == "__main__":
    unittest.main(verbosity=2)
