from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app import insert_sample_account

app = FastAPI(title="SVS Gold API")


# @app.get("/")
# async def root():
#     return {"status": "ok", "message": "FastAPI is running"}

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "ok"}

@app.post("/insert-sample")
async def insert_sample():
    try:
        account_id = insert_sample_account()
        return JSONResponse(status_code=201, content={"account_id": account_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
