import unittest
from solution import normalize_spaces

class PublicSpaceTests(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(normalize_spaces("  alpha \n beta\t gamma  "), "alpha beta gamma")

    def test_empty(self):
        self.assertEqual(normalize_spaces(""), "")

if __name__ == "__main__":
    unittest.main(verbosity=2)
