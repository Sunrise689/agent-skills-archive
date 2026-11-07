import unittest
from solution import chunked

class ChunkedTests(unittest.TestCase):
    def test_chunks(self):
        self.assertEqual(chunked([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
    def test_empty(self):
        self.assertEqual(chunked([], 3), [])
    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            chunked([1], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
