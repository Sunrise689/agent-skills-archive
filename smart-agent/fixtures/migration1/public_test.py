import unittest
from solution import first_nonempty

class FirstNonemptyTests(unittest.TestCase):
    def test_skips_empty_values(self):
        self.assertEqual(first_nonempty(["", "  ", "ok"]), "ok")
    def test_none_when_missing(self):
        self.assertIsNone(first_nonempty(["", " "]))
    def test_preserves_text(self):
        self.assertEqual(first_nonempty(["first", "second"]), "first")

if __name__ == "__main__":
    unittest.main(verbosity=2)
