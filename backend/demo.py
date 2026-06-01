"""Launch Eidos backend in demo mode."""
import os

os.environ["EIDOS_DEMO_MODE"] = "true"

if __name__ == "__main__":
    import uvicorn

    print("Starting Eidos in DEMO MODE")
    print("  In-memory database, no auth, no rate limit")
    print("  Open http://localhost:8000/docs")

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
