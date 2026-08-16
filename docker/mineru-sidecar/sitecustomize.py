"""Python 3.10 compatibility for the FileX MinerU 4 runtime.

MinerU 4 declares Python >=3.10 but imports ``datetime.UTC``, which
was added in Python 3.11.  The GPU image intentionally remains on Ubuntu
22.04/Python 3.10 because its CUDA wheels are pinned to cp310.  Python loads
this module automatically at interpreter startup, so both the deployment
probe and MinerU subprocesses receive the same small compatibility alias.
"""

import datetime


if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc
