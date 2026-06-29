"""Central safety defaults for bot runtime command/read paths.

Automatic background work stays disabled unless a future package changes these
constants deliberately and adds a dedicated safety gate.
"""

AUTO_SCAN_ON_BOT_START = False
AUTO_SCAN_ON_STATUS_READ = False
AUTO_SCAN_ON_DASHBOARD_READ = False
ENABLE_BACKGROUND_SCAN_WORKER = False

