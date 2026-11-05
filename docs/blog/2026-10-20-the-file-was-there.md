# The file was there

A developer copied Codex sessions from Windows into WSL2. REM discovered the project, but its path stayed `D:\Projects\PROJECT_NAME` while the same directory was available to the Linux process at `/mnt/d/Projects/PROJECT_NAME`. A file citation had the correct SHA-256, yet validation could not match the file to the mapped project.

The path mismatch was enough to explain the failure. On POSIX, REM now translates imported Windows drive paths with `wslpath -u` before using them to match the session working directory and project paths. The command receives the path as a separate argument; it does not pass through a shell. File evidence still has to resolve within the mapped project and match its SHA-256, including when the project is not a Git repository.

Regression tests cover the command arguments, imported working-directory metadata, saved project paths, and a hash-pinned file in a non-Git project. They exercise the conversion contract without requiring a live Windows Codex session or WSL installation.
