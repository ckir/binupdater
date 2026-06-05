import unittest
from unittest.mock import patch
from binupdater import _choose_multi

class TestChooseMulti(unittest.TestCase):
    @patch('builtins.input')
    def test_single_digits(self, mock_input):
        mock_input.side_effect = ["1 3 5"]
        options = ["bin1", "bin2", "bin3", "bin4", "bin5"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 2, 4])

    @patch('builtins.input')
    def test_simple_range(self, mock_input):
        mock_input.side_effect = ["1-3"]
        options = ["bin1", "bin2", "bin3", "bin4"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 1, 2])

    @patch('builtins.input')
    def test_range_and_comma_spaces(self, mock_input):
        mock_input.side_effect = ["1-3, 5, 2-4"]
        options = ["bin1", "bin2", "bin3", "bin4", "bin5"]
        result = _choose_multi("Select files", options)
        # Expected to preserve first occurrence order:
        # 1-3 -> [0, 1, 2]
        # 5 -> [4]
        # 2-4 -> [1, 2, 3] (1, 2 are duplicates and skipped)
        # Final result -> [0, 1, 2, 4, 3]
        self.assertEqual(result, [0, 1, 2, 4, 3])

    @patch('builtins.input')
    def test_spaces_around_hyphen(self, mock_input):
        mock_input.side_effect = ["1 - 3 , 5"]
        options = ["bin1", "bin2", "bin3", "bin4", "bin5"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 1, 2, 4])

    @patch('builtins.input')
    def test_descending_range(self, mock_input):
        mock_input.side_effect = ["3-1"]
        options = ["bin1", "bin2", "bin3", "bin4"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [2, 1, 0])

    @patch('builtins.input')
    def test_invalid_input_then_valid(self, mock_input):
        # First input is invalid (out of range, bad format), second is valid
        mock_input.side_effect = ["1-6", "invalid", "1-2"]
        options = ["bin1", "bin2", "bin3"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 1])

if __name__ == '__main__':
    unittest.main()
