import unittest
from solution import merge_defaults

class PublicMergeTests(unittest.TestCase):
    def test_merge_without_mutation(self):
        config = {"a": 2}
        defaults = {"a": 1, "b": 3}
        self.assertEqual(merge_defaults(config, defaults), {"a": 2, "b": 3})
        self.assertEqual(defaults, {"a": 1, "b": 3})

if __name__ == "__main__":
    unittest.main(verbosity=2)
