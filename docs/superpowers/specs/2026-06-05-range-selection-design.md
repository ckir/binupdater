# Design Spec: Accept Ranges in Executables Selection

**Date:** 2026-06-05  
**Topic:** Executable selection via ranges (e.g., 1-5,7,18-20) in `binupdater.py`  
**Status:** Approved  

---

## 1. Overview
The `binupdater` utility tracks and updates GitHub-released binaries. Currently, when adding a new tool with multiple files to extract, `_choose_multi` prompt allows selecting files by entering numbers separated by spaces.
To improve usability, we want to allow users to specify ranges (e.g. `1-5,7,18-20`) to select the executables to extract.

---

## 2. Requirements & Behavior
- Accept range strings such as `1-5,7,18-20`.
- Support multiple delimiters: spaces, commas, or both (e.g., `1-5, 7` or `1-5 7`).
- Robustly handle spaces around hyphens in ranges (e.g., `1 - 5`).
- Ensure duplicate and overlapping inputs (such as `1-3,2-4`) are de-duplicated while preserving the order of their first appearance.
- Support both ascending (e.g., `1-3`) and descending (e.g., `3-1`) ranges.
- Provide descriptive error messages if any selection is out of range or malformed.

---

## 3. Implementation Plan
We will update `_choose_multi` in `binupdater.py` to parse, validate, and expand inputs according to the requirements:

1. **Clean/Normalize Input**: Remove spaces surrounding any hyphens.
2. **Tokenize**: Split the raw string using regex `[,\s]+`.
3. **Parse and Validate**:
   - For parts containing hyphens, split by hyphen and convert to `(start, end)` range (inclusive). Validate that both are valid indices within options.
   - For simple digit parts, validate they represent a single valid option index.
   - Reject any other formats or out-of-bounds options with a helpful error.
4. **De-duplicate & Order Preservation**: Build the final index list while preserving the exact order of first occurrence.
