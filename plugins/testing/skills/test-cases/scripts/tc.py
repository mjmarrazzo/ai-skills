import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_cases.cli import main

raise SystemExit(main(sys.argv[1:]))
