# The wheel test that wasn't

The Windows check had turned green. It had built a wheel, installed it, and
opened REM's local snapshot twice. I was ready to treat that as evidence that
the preview would open on a Windows user's machine.

Then I looked at the command's working directory. The test launched Python
from the repository checkout. Python puts that directory on its import path
before the installed package. The wheel was present, but the code under test
could have been the source tree sitting beside the script. Green was not the
same as proven.

I moved the command into a fresh temporary directory outside the checkout.
The script stayed in the repository, but the subprocess that opened the reader
had no source package beside it. I built a wheel locally and ran that path
again before asking Windows CI to repeat it.

This was a release check for a bug that appears only after a user installs the
package on another operating system. Its boundary mattered more than its
assertions. A test called “installed wheel” must make the source checkout
unavailable, or it is testing a different product from the one we ship.
