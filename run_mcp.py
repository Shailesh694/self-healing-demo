from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from selfheal.mcp.__main__ import main

if __name__ == "__main__":
    main()
