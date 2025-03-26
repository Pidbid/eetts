# -*- encoding: utf-8 -*-
"""
@File    :   eetts.py
@Time    :   2025/03/26 16:12:14
@Author  :   Wicos
@Version :   1.0
@Contact :   wicos@wicos.cn
@Blog    :   https://www.wicos.me
@Desc    :   eetts main file
"""

# here put the import lib
import os
import time
import uvicorn
from pydantic import BaseModel
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, status
from edge_tts import Communicate, voices
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


# basemodels
class TTS(BaseModel):
    text: str
    token: str
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "0"
    volume: str = "0"
    pitch: str = "0"


app = FastAPI()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# background tasks
def delete_mp3_files(current_filename: str):
    while True:
        files = os.listdir("/output")
        for file in files:
            if file.endswith(".mp3"):
                file_path = os.path.join("/output", file)
                try:
                    if file_path == os.path.join("/output", current_filename):
                        continue
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
        time.sleep(60)  # 每分钟检查一次


# middleware
@app.middleware("http")
async def token_handler(request: Request, call_next):
    token = ""
    if request.method == "GET":
        token = request.query_params.get("token")
    elif request.method == "POST":
        token = await request.json().get("token")
    if not token or token != os.environ.get("TOKEN"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authorization token provided",
        )
    else:
        response = await call_next(request)
        return response


@app.get("/voices")
async def main(request: Request):
    voices_list = await voices.list_voices()
    return {"code": 0, "message": "success", "data": voices_list}


@app.api_route("/tts", methods=["GET", "POST"])
async def main(
    background_tasks: BackgroundTasks, request: Request, tts: TTS | None = None
):
    file_name = f"{int(time.time() * 1000)}.mp3"
    background_tasks.add_task(delete_mp3_files, file_name)
    text = ""
    voice = ""
    rate = ""
    volume = ""
    pitch = ""
    if request.method == "GET":
        text = (
            request.query_params.get("text")
            if request.query_params.get("text")
            else "您没有输入任何内容"
        )
        voice = (
            request.query_params.get("voice")
            if request.query_params.get("voice")
            else "zh-CN-XiaoxiaoNeural"
        )
        rate = (
            request.query_params.get("rate")
            if request.query_params.get("rate")
            else "0"
        )
        volume = (
            request.query_params.get("volume")
            if request.query_params.get("volume")
            else "0"
        )
        pitch = (
            request.query_params.get("pitch")
            if request.query_params.get("pitch")
            else "0"
        )
    elif request.method == "POST":
        text = tts.text
        voice = tts.voice
        rate = tts.rate
        volume = tts.volume
        pitch = tts.pitch
    communicate = Communicate(
        text=text,
        voice=voice,
        rate=f"+{rate}%",
        volume=f"+{volume}%",
        pitch=f"+{pitch}Hz",
    )
    save_path = f"/output/{file_name}"
    await communicate.save(save_path)
    return FileResponse(
        path=save_path, filename=file_name, media_type="application/octet-stream"
    )


if __name__ == "__main__":
    uvicorn.run("eetts:app", host="0.0.0.0", port=8000, log_level="debug", reload=True)
