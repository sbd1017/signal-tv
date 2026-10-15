import logging
import os

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
uvicorn.run("tvnext.server:app", host=os.environ.get("TVN_HOST", "127.0.0.1"), port=int(os.environ.get("TVN_PORT", "8792")),
            proxy_headers=False, access_log=False, log_level="info")
