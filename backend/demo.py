"""
Launch Eidos backend in demo mode.

Usage:
    python demo.py

No database, no auth, no external services required.
Everything runs in-memory — just install dependencies and go.
"""
import os

os.environ["EIDOS_DEMO_MODE"] = "true"

if __name__ == "__main__":
    import uvicorn

    print("\n?? Starting Eidos in DEMO MODE")
    print("   • In-memory database (no PostgreSQL needed)")
    print("   • Authentication disabled (no login required)")
    print("   • Rate limiting disabled")
    print("   • Open http://localhost:8000/docs for the interactive API\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
