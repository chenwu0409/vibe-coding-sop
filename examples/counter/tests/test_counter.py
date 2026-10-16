import unittest
from counter import count_nonempty


class CounterTests(unittest.TestCase):
    def test_mixed_lines(self):
        self.assertEqual(count_nonempty("alpha\n\n \nbeta\n"), 2)

    def test_empty(self):
        self.assertEqual(count_nonempty(""), 0)

    def test_unicode_and_windows_newlines(self):
        self.assertEqual(count_nonempty("你好\r\n\r\n世界"), 2)
