import unittest
from solution import dedupe_words

class PublicDedupeTests(unittest.TestCase):
    def test_preserves_first_seen_order(self):
        self.assertEqual(dedupe_words(["b", "a", "b", "c", "a"]), ["b", "a", "c"])

    def test_empty_input(self):
        self.assertEqual(dedupe_words([]), [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
