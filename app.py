import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import discovery
import nodes
import proxy

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    transport, cleanup_task = await discovery.start()
    proxy.start_client()
    yield

    cleanup_task.cancel()
    await proxy.close_client()
    transport.close()


app = FastAPI(title="DripDrop - Discovery", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to the React app's origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(discovery.router)
app.include_router(nodes.router)
app.include_router(proxy.router)
