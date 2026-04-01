<!--
name: 'Tool Description: Bash (sandbox — tmpdir)'
description: Use $TMPDIR for temporary files in sandbox mode
ccVersion: 2.1.86
-->
For temporary files, always use the `$TMPDIR` environment variable. TMPDIR is automatically set to the correct sandbox-writable directory in sandbox mode. Do NOT use `/tmp` directly - use `$TMPDIR` instead.
