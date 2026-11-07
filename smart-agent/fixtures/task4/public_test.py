import unittest
from solution import parse_bool

class PublicBoolTests(unittest.TestCase):
    def test_false_strings(self):
        self.assertIs(parse_bool("false"), False)
        self.assertIs(parse_bool("0"), False)

    def test_true_strings(self):
        self.assertIs(parse_bool("yes"), True)
        self.assertIs(parse_bool("1"), True)

if __name__ == "__main__":
    unittest.main(verbosity=2)
