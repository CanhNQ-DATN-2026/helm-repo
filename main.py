import asyncio
import logging
import uvicorn
from fastapi import FastAPI
from webhook.server import router, _run_claude
from bot.telegram import start_polling

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="AIOps Bot")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    asyncio.create_task(start_polling(_run_claude))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
