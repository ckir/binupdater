import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater
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


class MultiAssetTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.install_dir = self.root / "bin"
        self.install_path = self.install_dir / "foo.exe"

    def release(self, *names):
        return {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": name,
                    "browser_download_url": f"https://example.test/{name}",
                }
                for name in names
            ],
        }

    def zip_asset(self, name, files):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as z:
            for member, data in files.items():
                z.writestr(member, data)
        return path

    def download_from(self, payloads):
        def side_effect(url, dest, *args, **kwargs):
            shutil.copyfile(payloads[url.rsplit("/", 1)[-1]], dest)

        return side_effect


class TestReplaceBinary(unittest.TestCase):
    def test_locked_backup_does_not_fail_successful_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "new.exe"
            dest = root / "old.exe"
            src.write_bytes(b"new")
            dest.write_bytes(b"old")

            with (
                patch("updater.sys.platform", "win32"),
                patch.object(Path, "unlink", side_effect=OSError("locked")),
            ):
                updater.replace_binary(src, dest)

            self.assertEqual(dest.read_bytes(), b"new")
            self.assertTrue((root / "old.exe.bak").exists())


class TestUpdateToolMultipleAssets(MultiAssetTestCase):
    @patch("updater.config.get_platform", return_value="windows")
    @patch("updater.github_api.get_latest_release")
    @patch("updater.github_api.download_file")
    def test_installs_binaries_from_every_asset(
        self, mock_download, mock_release, mock_platform
    ):
        mock_release.return_value = self.release("foo-1.2.3.zip", "helper-1.2.3.zip")
        mock_download.side_effect = self.download_from(
            {
                "foo-1.2.3.zip": self.zip_asset("foo.zip", {"foo.exe": b"foo"}),
                "helper-1.2.3.zip": self.zip_asset(
                    "helper.zip", {"helper.exe": b"helper"}
                ),
            }
        )
        tool_config = {
            "repo": "example/foo",
            "platforms": {
                "windows": {
                    "install_path": str(self.install_path),
                    "assets": [
                        {
                            "asset_pattern": "foo-*.zip",
                            "files_in_archive": ["foo.exe"],
                            "binary_names": ["foo.exe"],
                        },
                        {
                            "asset_pattern": "helper-*.zip",
                            "files_in_archive": ["helper.exe"],
                            "binary_names": ["helper.exe"],
                        },
                    ],
                }
            },
        }

        result = updater.update_tool("foo", tool_config)

        self.assertEqual(result.status, "updated")
        self.assertEqual(self.install_path.read_bytes(), b"foo")
        self.assertEqual((self.install_dir / "helper.exe").read_bytes(), b"helper")
        self.assertEqual(mock_download.call_count, 2)

    @patch("updater.config.get_platform", return_value="windows")
    @patch("updater.github_api.get_latest_release")
    @patch("updater.github_api.download_file")
    def test_missing_extra_binary_updates_current_main_binary(
        self, mock_download, mock_release, mock_platform
    ):
        self.install_dir.mkdir(parents=True)
        self.install_path.write_bytes(b"old-main")
        mock_release.return_value = self.release("foo-1.2.3.zip", "helper-1.2.3.zip")
        mock_download.side_effect = self.download_from(
            {
                "foo-1.2.3.zip": self.zip_asset("foo.zip", {"foo.exe": b"foo"}),
                "helper-1.2.3.zip": self.zip_asset(
                    "helper.zip", {"helper.exe": b"helper"}
                ),
            }
        )
        tool_config = {
            "repo": "example/foo",
            "installed_version": "1.2.3",
            "platforms": {
                "windows": {
                    "install_path": str(self.install_path),
                    "assets": [
                        {
                            "asset_pattern": "foo-*.zip",
                            "files_in_archive": ["foo.exe"],
                            "binary_names": ["foo.exe"],
                        },
                        {
                            "asset_pattern": "helper-*.zip",
                            "files_in_archive": ["helper.exe"],
                            "binary_names": ["helper.exe"],
                        },
                    ],
                }
            },
        }

        result = updater.update_tool("foo", tool_config)

        self.assertEqual(result.status, "updated")
        self.assertEqual(self.install_path.read_bytes(), b"foo")
        self.assertEqual((self.install_dir / "helper.exe").read_bytes(), b"helper")
        self.assertEqual(mock_download.call_count, 2)

    @patch("updater.config.get_platform", return_value="windows")
    @patch("updater.github_api.get_latest_release")
    @patch("updater.github_api.download_file")
    def test_all_expected_binaries_present_stays_up_to_date(
        self, mock_download, mock_release, mock_platform
    ):
        self.install_dir.mkdir(parents=True)
        self.install_path.write_bytes(b"foo")
        (self.install_dir / "helper.exe").write_bytes(b"helper")
        mock_release.return_value = self.release("foo-1.2.3.zip", "helper-1.2.3.zip")
        tool_config = {
            "repo": "example/foo",
            "installed_version": "1.2.3",
            "platforms": {
                "windows": {
                    "install_path": str(self.install_path),
                    "assets": [
                        {
                            "asset_pattern": "foo-*.zip",
                            "files_in_archive": ["foo.exe"],
                            "binary_names": ["foo.exe"],
                        },
                        {
                            "asset_pattern": "helper-*.zip",
                            "files_in_archive": ["helper.exe"],
                            "binary_names": ["helper.exe"],
                        },
                    ],
                }
            },
        }

        result = updater.update_tool("foo", tool_config)

        self.assertEqual(result.status, "up_to_date")
        mock_download.assert_not_called()

    @patch("updater.config.get_platform", return_value="windows")
    @patch("updater.github_api.get_latest_release")
    @patch("updater.github_api.download_file")
    def test_legacy_single_asset_config_still_works(
        self, mock_download, mock_release, mock_platform
    ):
        mock_release.return_value = self.release("foo-1.2.3.zip")
        mock_download.side_effect = self.download_from(
            {"foo-1.2.3.zip": self.zip_asset("foo.zip", {"pkg/foo.exe": b"legacy"})}
        )
        tool_config = {
            "repo": "example/foo",
            "platforms": {
                "windows": {
                    "install_path": str(self.install_path),
                    "asset_pattern": "foo-*.zip",
                    "files_in_archive": ["pkg/foo.exe"],
                    "binary_names": ["foo.exe"],
                }
            },
        }

        result = updater.update_tool("foo", tool_config)

        self.assertEqual(result.status, "updated")
        self.assertEqual(self.install_path.read_bytes(), b"legacy")

    @patch("updater.config.get_platform", return_value="windows")
    @patch("updater.github_api.get_latest_release")
    @patch("updater.github_api.download_file")
    def test_missing_asset_reports_which_pattern_failed(
        self, mock_download, mock_release, mock_platform
    ):
        mock_release.return_value = self.release("foo-1.2.3.zip")
        tool_config = {
            "repo": "example/foo",
            "platforms": {
                "windows": {
                    "install_path": str(self.install_path),
                    "assets": [
                        {"asset_pattern": "foo-*.zip"},
                        {"asset_pattern": "missing-*.zip"},
                    ],
                }
            },
        }

        result = updater.update_tool("foo", tool_config)

        self.assertEqual(result.status, "error")
        self.assertIn("missing-*.zip", result.error)
        mock_download.assert_not_called()
        self.assertFalse(self.install_path.exists())

    @patch("updater.config.get_platform", return_value="windows")
    @patch("updater.github_api.get_latest_release")
    @patch("updater.github_api.download_file")
    def test_duplicate_destination_is_rejected_before_installing(
        self, mock_download, mock_release, mock_platform
    ):
        mock_release.return_value = self.release("foo-1.2.3.zip", "helper-1.2.3.zip")
        mock_download.side_effect = self.download_from(
            {
                "foo-1.2.3.zip": self.zip_asset("foo.zip", {"foo.exe": b"one"}),
                "helper-1.2.3.zip": self.zip_asset("helper.zip", {"foo.exe": b"two"}),
            }
        )
        tool_config = {
            "repo": "example/foo",
            "platforms": {
                "windows": {
                    "install_path": str(self.install_path),
                    "assets": [
                        {
                            "asset_pattern": "foo-*.zip",
                            "files_in_archive": ["foo.exe"],
                            "binary_names": ["foo.exe"],
                        },
                        {
                            "asset_pattern": "helper-*.zip",
                            "files_in_archive": ["foo.exe"],
                            "binary_names": ["foo.exe"],
                        },
                    ],
                }
            },
        }

        result = updater.update_tool("foo", tool_config)

        self.assertEqual(result.status, "error")
        self.assertIn("Duplicate", result.error)
        self.assertFalse(self.install_path.exists())


class TestAddMultipleAssets(MultiAssetTestCase):
    @patch("builtins.input")
    @patch("cli.config.save_config")
    @patch("cli.config.load_config")
    @patch("cli.shutil.which", return_value=None)
    @patch("cli._prompt")
    @patch("cli.github_api.get_repo_description", return_value="test tool")
    @patch("cli.github_api.get_latest_release")
    @patch("cli.github_api.download_file")
    def test_add_wizard_saves_multiple_assets(
        self,
        mock_download,
        mock_release,
        mock_description,
        mock_prompt,
        mock_which,
        mock_load_config,
        mock_save_config,
        mock_input,
    ):
        import cli

        mock_load_config.return_value = {}
        mock_release.return_value = self.release("foo-1.2.3.zip", "helper-1.2.3.zip")
        mock_download.side_effect = self.download_from(
            {
                "foo-1.2.3.zip": self.zip_asset("foo.zip", {"foo.exe": b"foo"}),
                "helper-1.2.3.zip": self.zip_asset(
                    "helper.zip", {"helper.exe": b"helper"}
                ),
            }
        )
        mock_input.side_effect = ["1 2", "n", "1", "1", "y"]
        mock_prompt.side_effect = [
            "foo.exe",
            "helper.exe",
            str(self.install_path),
            str(self.install_dir / "helper.exe"),
            "--version",
            "(.*)",
        ]

        class Args:
            url = "https://github.com/example/foo"
            name = None
            force = True

        cli.cmd_add(Args())

        saved = mock_save_config.call_args[0][0]
        platform_cfg = saved["tools"]["foo"]["platforms"]["windows"]
        self.assertEqual(
            [asset["asset_pattern"] for asset in platform_cfg["assets"]],
            ["foo-*.zip", "helper-*.zip"],
        )
        self.assertEqual(self.install_path.read_bytes(), b"foo")
        self.assertEqual((self.install_dir / "helper.exe").read_bytes(), b"helper")


if __name__ == "__main__":
    unittest.main()
