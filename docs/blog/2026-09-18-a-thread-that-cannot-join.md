# A thread that could stop, but could not join

The service restarted successfully, yet its shutdown log contained a TypeError. The cleanup thread had finished its loop. The failure came afterward, when Python tried to join it.

The thread kept its cancellation event in `self._stop`. That name already belongs to `threading.Thread`: joining a finished thread calls its internal `_stop()` method. Our Event replaced that method, so normal shutdown tried to call an Event.

Renaming the field to `_stop_event` leaves the standard thread lifecycle intact. A regression test starts a real cleanup thread, stops it twice, joins it again, and checks that it is no longer alive. Before the rename, the first stop fails with the same TypeError as the service. Afterward, all three waits succeed.

A successful restart only proves the new process came up. It says nothing about whether the old process shut down cleanly. That distinction is why this test exercises the actual thread rather than mocking `join`.
