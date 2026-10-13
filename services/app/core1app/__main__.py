import importlib
import os

import uvicorn

from .common import setup_logging

SERVICE = os.environ.get("CORE1_SERVICE", "gateway").replace("-", "_")
PORT = int(os.environ.get("PORT", "8080"))

setup_logging()
module = importlib.import_module(f"core1app.{SERVICE}")
uvicorn.run(module.app, host="0.0.0.0", port=PORT, log_config=None, access_log=False)
