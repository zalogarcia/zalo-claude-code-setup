Build or rebuild the repo-graphrag knowledge graph for the current project.

Usage: /graph [repo_path]

- If no path given, use the current working directory
- Storage name is auto-derived: `storage_<repo-dirname>`

## Steps

1. Determine the repo path (argument or cwd) and derive `storage_name` as `storage_<basename of repo path>`
2. Run `graph_create` MCP tool with:
   - `read_dir_path`: the repo path
   - `storage_name`: the derived storage name
3. Report the result — how many files were processed, whether it was a fresh build or incremental update
4. If `graph_create` fails, fall back to the CLI: `cd ~/repo-graphrag-mcp && uv run python cli_create.py <repo_path> <storage_name>`
