import unittest
from solution import partition_even

class PartitionTests(unittest.TestCase):
    def test_groups_and_preserves_order(self):
        self.assertEqual(partition_even([3, 2, 4, 1, 6]), ([2, 4, 6], [3, 1]))
    def test_empty(self):
        self.assertEqual(partition_even([]), ([], []))
    def test_negative_numbers(self):
        self.assertEqual(partition_even([-3, -2, 0]), ([-2, 0], [-3]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
