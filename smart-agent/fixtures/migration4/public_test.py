import unittest
from solution import deep_merge

class DeepMergeTests(unittest.TestCase):
    def test_nested_merge(self):
        base = {"db": {"host": "localhost", "port": 5432}, "debug": False}
        patch = {"db": {"port": 5433}}
        self.assertEqual(deep_merge(base, patch), {"db": {"host": "localhost", "port": 5433}, "debug": False})
        self.assertEqual(base["db"]["port"], 5432)
    def test_new_keys(self):
        self.assertEqual(deep_merge({"a": 1}, {"b": 2}), {"a": 1, "b": 2})
    def test_patch_wins_scalar(self):
        self.assertEqual(deep_merge({"a": {"x": 1}}, {"a": 2}), {"a": 2})

if __name__ == "__main__":
    unittest.main(verbosity=2)
