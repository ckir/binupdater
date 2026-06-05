# Spec: Resilient Binary Extraction and Installation

This specification details the design for introducing resilient binary extraction/installation in `binupdater`, ensuring that when copying or extracting multiple binaries for a tool, any failures (such as `PermissionError` due to lack of elevated privileges) do not abort the process. Instead, the utility continues to install the remaining binaries and displays a summary of all failures at the end of execution.

## Requirements

1. **Continue on Failure**: When installing multiple binaries (either during interactive `add` or automated `update`), a failure to install one binary must not prevent others from being installed.
2. **Handle Permission and General Errors**: Catch `PermissionError` (printing an elevated privilege hint) and other general `Exception` types.
3. **Consolidated Summary**:
   - During `add`: Print a summary of failed files at the end of the installation process.
   - During `update`: Continue updating other tools, and print a consolidated "Summary of Failed Updates" listing all failed tools and their specific errors at the end of the run.

## Component Design

### 1. `cli.py` (`add` command)
The installation loop in `add` (where binaries extracted to the temp directory are copied to their final paths) will be modified to handle exceptions individually for each binary.

**Target File**: `cli.py`
**Target lines**: `~308-316`

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

### 2. `updater.py` (`update_tool` function)
The binary replacement logic will group the main binary and all extra files, attempt to replace each one, log any failures, and continue replacing the rest. If any fail, it will return `UpdateResult(..., status="error", error="...")`.

**Target File**: `updater.py`
**Target lines**: `~203-213`

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

### 3. `cli.py` (`cmd_update` function)
At the end of updating all tools, `cmd_update` will inspect the results list and print a summary of all tools that failed during the process.

**Target File**: `cli.py`
**Target lines**: `~419-428`

```python
    failed_updates = [r for r in results if r.status == "error"]
    if failed_updates:
        print("\n--- Summary of Failed Updates ---")
        for r in failed_updates:
            print(f"  Tool: {r.tool}")
            print(f"    Error: {r.error}")
```

## Testing Plan

1. **Interactive Unit Tests**: Mock `replace_binary` to throw `PermissionError` on specific paths to verify that others continue to install, and check stdout prints the expected summary.
2. **Integration Checks**: Run end-to-end checks where some destination directories have restricted permissions to verify proper "Permission denied" resilience.
