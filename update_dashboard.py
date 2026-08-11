"""Convenience wrapper: pull fresh Help Scout data, then regenerate the TV board.

Equivalent to running:
    python export_helpscout.py
    python generate_tv_dashboard.py
"""

import export_helpscout
import generate_tv_dashboard

if __name__ == "__main__":
    export_helpscout.main()
    print()
    generate_tv_dashboard.main()
