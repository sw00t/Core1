import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DB_DSN", "memory://")
os.environ.setdefault("DB_QUERY_COST_MS", "5")
os.environ.setdefault("LOG_LEVEL", "warning")
