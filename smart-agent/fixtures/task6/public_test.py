import unittest
from solution import running_totals

class PublicTotalTests(unittest.TestCase):
    def test_positive_values(self):
        self.assertEqual(running_totals([1, 2, 3]), [1, 3, 6])

    def test_empty(self):
        self.assertEqual(running_totals([]), [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
