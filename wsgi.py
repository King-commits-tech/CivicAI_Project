
import threading

from app import app, monitor_loop
from core.seed import seed

seed()

threading.Thread(
    target=monitor_loop,
    daemon=True
).start()
