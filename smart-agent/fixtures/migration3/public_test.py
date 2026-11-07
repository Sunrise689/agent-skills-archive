import unittest
from solution import parse_kv

class ParseKVTests(unittest.TestCase):
    def test_trim_and_duplicate(self):
        self.assertEqual(parse_kv(" a = 1; b=2; a=3 "), {"a": "3", "b": "2"})
    def test_ignores_bare_items(self):
        self.assertEqual(parse_kv("x=1;bad;y=2"), {"x": "1", "y": "2"})
    def test_value_can_contain_equals(self):
        self.assertEqual(parse_kv("token=a=b"), {"token": "a=b"})

if __name__ == "__main__":
    unittest.main(verbosity=2)
