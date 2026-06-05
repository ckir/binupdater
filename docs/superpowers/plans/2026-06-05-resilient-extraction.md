# Resilient Extraction and Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure that any permission or general failure when copying or installing individual binaries during `add` or `update` does not halt execution, allowing remaining binaries to install, and outputs a summary of failures at the end of the run.

**Architecture:** Maintain an error collection array during file replacement in `cli.py` (for manual installations) and `updater.py` (for automated tool updates). Then, format and print consolidated summaries at the end of the command executions.

**Tech Stack:** Python 3 standard library

---

### Task 1: Refactor `updater.py` (Resilient Update Tool Installations)

**Files:**
- Modify: `C:\Users\user\Development\Python\binupdater\updater.py:203-213`
- Test: `C:\Users\user\Development\Python\binupdater\test_binupdater.py`

- [ ] **Step 1: Inspect updater.py**
  Review `update_tool` around line 203-213 to find where files are replaced.

- [ ] **Step 2: Update replacement block in update_tool**
  Replace lines 203-213 with the following resilient, continue-on-failure block:

```python
        install_dir = binary_path.parent
        binaries_to_install = [(extracted, binary_path)]
        for extra in extra_files:
            binaries_to_install.append((extra, install_dir / extra.name))

        failed_binaries = []
        for src, dest in binaries_to_install:
            try:
                replace_binary(src, dest)
            except PermissionError:
                failed_binaries.append((dest.name, "Permission denied. You may need elevated privileges."))
            except Exception as e:
                failed_binaries.append((dest.name, str(e)))

        if failed_binaries:
            err_msg = "; ".join(f"{name} ({err})" for name, err in failed_binaries)
            return UpdateResult(
                tool_name,
                "error",
                old_version=installed,
                new_version=latest_ver,
                error=f"Some binaries failed to replace: {err_msg}"
            )
```

- [ ] **Step 3: Run existing unit tests**
  Run: `python -m unittest test_binupdater.py`
  Expected: All 6 tests pass successfully.

- [ ] **Step 4: Commit**
  Run:
  ```bash
  git add updater.py
  git commit -m "refactor: implement resilient binary replacement in updater.py"
  ```

---

### Task 2: Refactor `cli.py` (Resilient `add` command installations)

**Files:**
- Modify: `C:\Users\user\Development\Python\binupdater\cli.py:307-316`
- Test: `C:\Users\user\Development\Python\binupdater\test_binupdater.py`

- [ ] **Step 1: Inspect cli.py**
  Review the installer loop in `add` command around lines 307-316.

- [ ] **Step 2: Update the installer loop in cli.py**
  Replace lines 307-316 with the following resilient logic and final summary printout:

```python
            if (missing and ans != "n") or (not missing and ans == "y"):
                succeeded = []
                failed = []
                for i, src in enumerate(current_extracted):
                    dest = Path(current_install_paths[i])
                    try:
                        updater.replace_binary(src, dest)
                        succeeded.append((src.name, dest))
                    except PermissionError:
                        print(f"  Error: Permission denied writing to {dest.name}.")
                        failed.append((dest, "Permission denied. You may need elevated privileges."))
                    except Exception as e:
                        print(f"  Error: Failed to replace {dest.name}: {e}")
                        failed.append((dest, str(e)))

                if succeeded:
                    print(f"Installed {len(succeeded)} file(s) to {main_dest.parent}")
                if failed:
                    print("\n[!] Summary of Failed Extractions/Installations:")
                    for dest, err in failed:
                        print(f"  - {dest}: {err}")
```

- [ ] **Step 3: Run tests to verify correctness**
  Run: `python -m unittest test_binupdater.py`
  Expected: PASS

- [ ] **Step 4: Commit**
  Run:
  ```bash
  git add cli.py
  git commit -m "feat: add resilient copy-on-write during tool additions"
  ```

---

### Task 3: Implement consolidated Summary in `cmd_update` (`cli.py`)

**Files:**
- Modify: `C:\Users\user\Development\Python\binupdater\cli.py:416-428`
- Test: `C:\Users\user\Development\Python\binupdater\test_binupdater.py`

- [ ] **Step 1: Modify cmd_update in cli.py**
  Append a clear consolidated Summary of Failed Updates at the end of the update function. Change lines 416-428:

```python
    if not check_only or config_dirty:
        config.save_config(cfg_data)

    parts = []
    if n := sum(1 for r in results if r.status == "updated"):
        parts.append(f"{n} updated")
    if n := sum(1 for r in results if r.status == "up_to_date"):
        parts.append(f"{n} up to date")
    if n := sum(1 for r in results if r.status == "update_available"):
        parts.append(f"{n} updates available")
    if n := sum(1 for r in results if r.status == "error"):
        parts.append(f"{n} error(s)")
    print(f"\nDone: {', '.join(parts) or 'nothing to do'}")

    failed_updates = [r for r in results if r.status == "error"]
    if failed_updates:
        print("\n--- Summary of Failed Updates ---")
        for r in failed_updates:
            print(f"  Tool: {r.tool}")
            print(f"    Error: {r.error}")
```

- [ ] **Step 2: Verify runtime syntax**
  Run: `python -m py_compile cli.py`
  Expected: Successful compilation without error.

- [ ] **Step 3: Commit**
  Run:
  ```bash
  git add cli.py
  git commit -m "feat: print consolidated failure summary at end of cmd_update"
  ```

---

### Task 4: Create unit tests for resilient installation and summaries

**Files:**
- Create/Modify: `C:\Users\user\Development\Python\binupdater\test_binupdater.py`

- [ ] **Step 1: Add new unit tests to test_binupdater.py**
  Add test cases mocking file extraction errors and verifying that execution continues, and check output for the failure summary. Append these tests to `test_binupdater.py`:

```python
    @patch('builtins.input')
    @patch('updater.replace_binary')
    @patch('cli.shutil.which')
    @patch('cli._prompt')
    @patch('cli.github_api.get_latest_release')
    @patch('cli.github_api.download_file')
    @patch('cli.archive.is_archive')
    @patch('cli.archive.list_archive')
    @patch('cli.archive.find_in_archive')
    @patch('cli.archive.extract_file')
    @patch('sys.stdout', new_callable=unittest.mock.MagicMock)
    def test_add_resilient_install(self, mock_stdout, mock_extract, mock_find, mock_list, mock_is_arch, mock_download, mock_release, mock_prompt, mock_which, mock_replace, mock_input):
        import cli
        # Setup mocks for adding a tool with 2 files where 1 fails
        mock_input.side_effect = ["n", "1, 2", "name1", "name2", "y", "C:\\test\\path\\1", "C:\\test\\path\\2"]
        mock_release.return_value = {"tag_name": "v1.0.0", "description": "test", "assets": [{"name": "test.zip", "browser_download_url": "url"}]}
        mock_is_arch.return_value = True
        mock_list.return_value = ["bin1", "bin2"]
        mock_find.side_effect = ["bin1", "bin2"]
        mock_which.return_value = None
        mock_prompt.side_effect = ["name1", "name2", "C:\\test\\path\\1", "C:\\test\\path\\2"]
        
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
        stdout_calls = [call[0][0] for call in mock_stdout.write.call_args_list if call[0]]
        full_stdout = "".join(stdout_calls)
        self.assertIn("Summary of Failed Extractions/Installations", full_stdout)
```

- [ ] **Step 2: Run all unit tests**
  Run: `python -m unittest test_binupdater.py`
  Expected: PASS

- [ ] **Step 3: Commit**
  Run:
  ```bash
  git add test_binupdater.py
  git commit -m "test: add unit test for resilient binary installation and summary"
  ```
