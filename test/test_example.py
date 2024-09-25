import unittest
from src.example import vector_length


class TestMathOperations(unittest.TestCase):
    def test_vector_length(self):
        result = vector_length([3, 4])
        self.assertEqual(result, 5.0)


if __name__ == "__main__":
    unittest.main()
