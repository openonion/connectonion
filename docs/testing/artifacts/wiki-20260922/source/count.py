from pathlib import Path
import sys
print(len(Path(sys.argv[1]).read_text().split()))
