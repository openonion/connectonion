---
title: "Live should start its Host"
date: 2026-10-07
---

The owner asked REM to open live. The terminal reported that it had launched a page, printed a temporary file link, and then explained that the Host was offline. To get the requested view, the owner needed to run `co ai` and repeat the command.

“it should start the co ai automatically,” they replied.

The presence check was doing its job: it prevented a browser tab that could not load. But it stopped one step too early. The command knew which Host it needed and had a way to start it, yet passed that dependency back to the person who had just asked to open their notebook.

The fix uses the existing co ai Host. An online Host is reused; an offline one is started in the background. That start suppresses channel listeners and the usual extra chat tab. REM waits for reachability before handing the live URL to the browser. A failed start still offers the offline notebook, explicitly labels it a snapshot, and returns a failure status with a local log path.

An independent AI review found a less visible problem in the first implementation. A saved PID could outlive its process. If the operating system reused that number, later opens would keep waiting for an unrelated program. The state now records the managed command and verifies its owner before reusing it. The review also caught corrupt startup state bypassing the fallback; a regression now preserves that file and checks the fallback.

The isolated verification run passed 148 tests across startup, reader CLI behavior and the existing co ai server paths. It made no real model calls or mailbox scans. The owner will test the actual live experience manually; this record does not claim that a mock readiness response proves the relay connection works on their account.

The lesson here is small and concrete: when a command promises a view, starting the service required to show it belongs in that command's flow. The offline fallback remains useful, but its success cannot stand in for the live view the person requested.
