from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.routers import opportunities

app = FastAPI(
    title="NYC Taxi Opportunities & Efficiency API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register only the opportunities router
app.include_router(opportunities.router)


@app.get("/")
def root():
    return {"message": "NYC Taxi API is running"}