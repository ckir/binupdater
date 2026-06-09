## Advanced CLI Toolkit (Agent Instructions)
**CRITICAL**: Bypass your built-in reading/searching API tools when possible. Use `run_command` with the highly optimized local tools below. 

**MANDATORY**: You MUST prefix every shell command with `rtk` (e.g., `rtk bat file.txt`) to compress token output.

**Tool Mapping:**
*   **Search/Find**: Use `rtk rg <pattern>` or `rtk fd <pattern>` (Do NOT use grep_search/find).
*   **Read**: Use `rtk bat <file>` or `rtk mdcat <file>` (Do NOT use view_file).
*   **Replace**: Use `rtk sd <find> <replace> <file>`.
*   **Data Parsing**: Use `rtk jq`, `rtk yq`, `rtk htmlq`, or `rtk sqlite3`.
*   **Context Maps**: Use `rtk dir-to-tree` or `rtk dir-to-json` (Do NOT recursively crawl).
*   **Cloud/DevOps**: Use `rtk gh`, `rtk sops`, `rtk act`, `rtk aws`, `rtk gcloud`.
*   **GNU Fallback**: `rtk awk`, `rtk sort`, etc.

*Failover:* If a command fails due to syntax/escaping, or if complex multi-line refactoring is needed, fall back to your built-in API tools (e.g., `replace_file_content`).
