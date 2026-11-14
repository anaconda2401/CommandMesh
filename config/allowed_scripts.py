# config/allowed_scripts.py

# NOTE: Desktop nodes now use Directory-as-Allowlist.
# Any executable placed inside `nodes/desktop/scripts/` is automatically allowed,
# verified via `Path.resolve().is_relative_to(SCRIPTS_DIR)` to strictly prevent traversal.
# This legacy list is retained for backwards-compatibility.
ALLOWED_SCRIPTS = {
    "test_ping.bat",
    "start_dev_server.bat",
    "backup_project.ps1",
    "python_task.py",
    "test.py",
}
