"""Production entry point: uvicorn on cfg.host:cfg.port. The Windows service runs this."""

import logging

import uvicorn

from teip.app import app

if __name__ == "__main__":
    cfg = app.state.cfg
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(app, host=cfg.host, port=cfg.port, proxy_headers=True)
