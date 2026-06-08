import unittest
from unittest.mock import patch

from cli import _choose_multi


class TestChooseMulti(unittest.TestCase):
    @patch("builtins.input")
    def test_single_digits(self, mock_input):
        mock_input.side_effect = ["1 3 5"]
        options = ["bin1", "bin2", "bin3", "bin4", "bin5"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 2, 4])

    @patch("builtins.input")
    def test_simple_range(self, mock_input):
        mock_input.side_effect = ["1-3"]
        options = ["bin1", "bin2", "bin3", "bin4"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 1, 2])

    @patch("builtins.input")
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

    @patch("builtins.input")
    def test_spaces_around_hyphen(self, mock_input):
        mock_input.side_effect = ["1 - 3 , 5"]
        options = ["bin1", "bin2", "bin3", "bin4", "bin5"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 1, 2, 4])

    @patch("builtins.input")
    def test_descending_range(self, mock_input):
        mock_input.side_effect = ["3-1"]
        options = ["bin1", "bin2", "bin3", "bin4"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [2, 1, 0])

    @patch("builtins.input")
    def test_invalid_input_then_valid(self, mock_input):
        # First input is invalid (out of range, bad format), second is valid
        mock_input.side_effect = ["1-6", "invalid", "1-2"]
        options = ["bin1", "bin2", "bin3"]
        result = _choose_multi("Select files", options)
        self.assertEqual(result, [0, 1])

    @patch("builtins.input")
    @patch("cli.config.save_config")
    @patch("cli.config.load_config")
    @patch("updater.replace_binary")
    @patch("cli.shutil.which")
    @patch("cli._prompt")
    @patch("cli.github_api.get_latest_release")
    @patch("cli.github_api.download_file")
    @patch("cli.archive.is_archive")
    @patch("cli.archive.list_archive")
    @patch("cli.archive.find_in_archive")
    @patch("cli.archive.extract_file")
    @patch("sys.stdout", new_callable=unittest.mock.MagicMock)
    def test_add_resilient_install(
        self,
        mock_stdout,
        mock_extract,
        mock_find,
        mock_list,
        mock_is_arch,
        mock_download,
        mock_release,
        mock_prompt,
        mock_which,
        mock_replace,
        mock_load_config,
        mock_save_config,
        mock_input,
    ):
        import cli

        mock_load_config.return_value = {}

        # Setup mocks for adding a tool with 2 files where 1 fails
        inputs = ["1", "n", "1, 2", "y"]
        mock_input.side_effect = inputs
        mock_prompt.side_effect = [
            "name1",
            "name2",
            "C:\\test\\path\\name1",
            "C:\\test\\path\\name2",
            "--version",
            "(.*)",
        ]
        mock_release.return_value = {
            "tag_name": "v1.0.0",
            "description": "test",
            "assets": [{"name": "test.zip", "browser_download_url": "url"}],
        }
        mock_is_arch.return_value = True
        mock_list.return_value = ["bin1", "bin2"]
        mock_find.side_effect = ["bin1", "bin2"]
        mock_which.return_value = None

        # Make the first replace fail, second succeed
        def side_effect(src, dest):
            if "name1" in str(dest):
                raise PermissionError("Permission denied")
            return None

        mock_replace.side_effect = side_effect

        # Prepare args
        class Args:
            url = "https://github.com/test/test"
            name = None
            force = True

        cli.cmd_add(Args())

        # Verify both paths were attempted and the summary is printed
        self.assertEqual(mock_replace.call_count, 2)
        # Verify the stdout printout includes the summary
        stdout_calls = [
            call[0][0] for call in mock_stdout.write.call_args_list if call[0]
        ]
        full_stdout = "".join(stdout_calls)
        self.assertIn("Summary of Failed Extractions/Installations", full_stdout)


if __name__ == "__main__":
    unittest.main()
