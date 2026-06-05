# Range Selection in Executables List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `binupdater.py` to accept ranges (e.g., `1-5,7,18-20`) in the interactive executable selection prompt, de-duplicating selections while preserving the first-appearance order.

**Architecture:** We will replace the current space/comma splitter in `_choose_multi` with a robust tokenizer using `re.split()`. It will normalize spacing around range hyphens, parse individual numbers and range sequences, de-duplicate while retaining the selection order, and validate correctness.

**Tech Stack:** Python 3 (standard library: `re`, `unittest`, `unittest.mock`).

---

### Task 1: Create Unit Tests for `_choose_multi`

We will create a test file `test_binupdater.py` to test the range parsing behavior. We will mock `input()` and check the return value of `_choose_multi`.

**Files:**
- Create: `test_binupdater.py`

- [ ] **Step 1: Write the tests**

Write the following test suite in `test_binupdater.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails/errors**

Run: `python -m unittest test_binupdater.py`  
Expected: Failure or error because `_choose_multi` does not handle hyphens and will treat them as invalid tokens under current implementation.

- [ ] **Step 3: Commit the test file**

```bash
git add test_binupdater.py
git commit -m "test: add unit tests for _choose_multi range parsing"
```

---

### Task 2: Implement Range Parsing in `_choose_multi`

We will modify `binupdater.py` to support ranges and pass the unit tests.

**Files:**
- Modify: `binupdater.py:411-434`
- Test: `test_binupdater.py`

- [ ] **Step 1: Modify `_choose_multi` in `binupdater.py`**

Replace the current implementation of `_choose_multi` (around line 411) with:

```python
def _choose_multi(prompt: str, options: list[str]) -> list[int]:
    for i, opt in enumerate(options, 1):
        print(f"  {i:3}. {opt}")
    print(f"  {prompt}")
    print("  Enter numbers or ranges (e.g. 1-5,7,18-20) — first selection is the main binary.")
    while True:
        raw = input("  > ").strip()
        
        # Normalize: remove spaces around hyphens (e.g. "1 - 5" -> "1-5")
        raw = re.sub(r'\s*-\s*', '-', raw)
        
        # Split by commas or spaces
        parts = re.split(r'[,\s]+', raw)
        parts = [p for p in parts if p]  # filter out empty elements
        
        indices: list[int] = []
        ok = True
        
        for p in parts:
            if "-" in p:
                subparts = p.split("-")
                if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                    start, end = int(subparts[0]), int(subparts[1])
                    if 1 <= start <= len(options) and 1 <= end <= len(options):
                        # Support ranges both ascending and descending
                        step = 1 if start <= end else -1
                        for val in range(start, end + step, step):
                            idx = val - 1
                            if idx not in indices:
                                indices.append(idx)
                    else:
                        print(f"  Invalid range: '{p}'. Enter numbers between 1 and {len(options)}.")
                        ok = False
                        break
                else:
                    print(f"  Invalid format: '{p}'. Enter numbers or ranges like 1-5.")
                    ok = False
                    break
            elif p.isdigit():
                val = int(p)
                if 1 <= val <= len(options):
                    idx = val - 1
                    if idx not in indices:
                        indices.append(idx)
                else:
                    print(f"  Invalid: '{p}'. Enter numbers between 1 and {len(options)}.")
                    ok = False
                    break
            else:
                print(f"  Invalid format: '{p}'. Enter numbers or ranges like 1-5.")
                ok = False
                break
                
        if ok and indices:
            return indices
        if ok:
            print("  Select at least one file.")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m unittest test_binupdater.py`  
Expected: PASS (6 tests run successfully)

- [ ] **Step 3: Commit changes**

```bash
git add binupdater.py
git commit -m "feat: implement range and comma-separated selection in _choose_multi"
```

---

### Task 3: Clean up and Verification

We will clean up any temporary files or verify the final state.

**Files:**
- Modify: None (cleanup and verify)

- [ ] **Step 1: Run complete test suite and linters if available**

Run: `python -m unittest test_binupdater.py`  
Expected: PASS

- [ ] **Step 2: Verify `git status` is clean**

Ensure that only `binupdater.py`, `test_binupdater.py`, and the design documents are modified/added.
