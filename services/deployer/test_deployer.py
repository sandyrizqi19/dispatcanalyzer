import asyncio
import json
import sys
from services.deployer.pipeline import DeploymentPipeline

async def test_pipeline():
    print("Testing DeploymentPipeline initialization...")
    pipeline = DeploymentPipeline()
    summary = pipeline.get_summary()
    assert summary["status"] == "idle"
    assert summary["is_running"] is False
    assert len(summary["stages"]) == 6
    print("✓ Pipeline initial state valid.")

    print("Testing event subscription and broadcasting...")
    queue = pipeline.add_subscriber()
    await pipeline.broadcast({"type": "test_event", "data": "hello"})
    msg = await queue.get()
    parsed = json.loads(msg)
    assert parsed["type"] == "test_event"
    assert parsed["data"] == "hello"
    pipeline.remove_subscriber(queue)
    print("✓ Event subscription and broadcasting valid.")

    print("Testing logging mechanism...")
    await pipeline.log("Test log entry", level="info", stage=1)
    assert len(pipeline.logs) >= 1
    assert pipeline.logs[-1]["message"] == "Test log entry"
    assert pipeline.logs[-1]["level"] == "info"
    print("✓ In-memory log buffer valid.")

    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_pipeline())
