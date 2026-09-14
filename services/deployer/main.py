import asyncio
import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from .pipeline import pipeline_instance

app = FastAPI(title="Dispatch Intelligence - Deployment Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

class DeployTriggerRequest(BaseModel):
    pre_build_first: bool = True
    skip_docker: bool = False
    auth_token: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    if not os.path.exists(TEMPLATE_PATH):
        raise HTTPException(status_code=404, detail="Template index.html tidak ditemukan")
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "deploy-manager"}

@app.get("/api/deploy/status")
async def get_status():
    return pipeline_instance.get_summary()

@app.post("/api/deploy/start")
async def trigger_deploy(body: DeployTriggerRequest):
    # Optional Auth Token Check
    required_token = os.getenv("DEPLOYER_AUTH_TOKEN", "").strip()
    if required_token and body.auth_token != required_token:
        raise HTTPException(status_code=401, detail="Token otorisasi deployment tidak valid")

    if pipeline_instance.is_running:
        raise HTTPException(status_code=400, detail="Deployment sedang berlangsung. Harap tunggu hingga selesai.")

    # Start background task
    asyncio.create_task(
        pipeline_instance.execute(
            pre_build_first=body.pre_build_first,
            skip_docker=body.skip_docker
        )
    )

    return {
        "status": "started",
        "message": "Pipeline deployment berhasil dimulai",
        "summary": pipeline_instance.get_summary()
    }

@app.get("/api/deploy/stream")
async def stream_logs(request: Request):
    """Server-Sent Events (SSE) streaming endpoint."""
    queue = pipeline_instance.add_subscriber()

    async def event_generator():
        try:
            # First, catch up with existing logs if any
            for log_entry in pipeline_instance.logs:
                yield f"data: {json.dumps({'type': 'log', 'data': log_entry})}\n\n"

            # Send current pipeline state
            yield f"data: {json.dumps({'type': 'stage', 'stage': pipeline_instance.current_stage, 'status': pipeline_instance.current_status})}\n\n"

            while True:
                # Disconnect check
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next event or keepalive timeout
                    event_str = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {event_str}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping to prevent proxy/browser timeout
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            pipeline_instance.remove_subscriber(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DEPLOYER_PORT", "8080"))
    uvicorn.run("services.deployer.main:app", host="0.0.0.0", port=port, reload=False)
