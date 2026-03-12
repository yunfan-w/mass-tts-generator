import os
import io
import argparse
import torch
import torchaudio
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import uvicorn
from qwen_tts import Qwen3TTSModel

app = FastAPI(title="Qwen3-TTS-Base Clone API (Static Prompt)")

# ================= 核心配置区 =================
# 提前把女生音频放在和 api.py 同一个目录下
REF_AUDIO_PATH = "lxy_english_8db.wav"  # 替换成你的真实文件名
REF_TEXT = "The lessons you've learn in the growth and experience is never spontaneous. It's always meant to be. There's a higher purpose, a goal, a final destination, or a peak in your journey that you have no idea of until you reach it. " # 替换成她说的真实英文
# ==============================================

# 接口极度精简，前端只管闭着眼睛塞文本就行了
class TTSRequest(BaseModel):
    text: str
    language: str = "English"
    format: str = "wav"

model = None
global_voice_prompt = None  # 用于在显存中常驻女生的声纹特征

@app.on_event("startup")
async def load_model():
    global model, global_voice_prompt
    print(f"[{os.getpid()}] 1. 正在加载 Qwen3-TTS-Base 模型...")
    
    model = Qwen3TTSModel.from_pretrained(
        "./Qwen3-TTS-12Hz-1.7B-Base",
        device_map="cuda", 
        dtype=torch.bfloat16,
        attn_implementation="flash_attention_2"
    )
    
    print(f"[{os.getpid()}] 2. 正在提取并固化女生声纹特征...")
    # 核心优化：只在启动时提取一次，永远驻留显存！
    global_voice_prompt = model.create_voice_clone_prompt(
        ref_audio=REF_AUDIO_PATH,
        ref_text=REF_TEXT
    )
    print(f"[{os.getpid()}] ✅ 模型和专属声纹均已加载完毕，随时接客！")

@app.post("/api/tts")
async def generate_speech(req: TTSRequest):
    if model is None or global_voice_prompt is None:
        raise HTTPException(status_code=500, detail="模型或声纹未初始化")
        
    try:
        # 直接使用预热好的 voice_clone_prompt，跳过特征提取阶段
        wavs, sr = model.generate_voice_clone(
            text=req.text,
            language=req.language,
            voice_clone_prompt=global_voice_prompt
        )
        
        buffer = io.BytesIO()
        torchaudio.save(
            buffer, 
            torch.tensor(wavs[0]).unsqueeze(0), 
            sr, 
            format=req.format
        )
        return Response(content=buffer.getvalue(), media_type="audio/wav")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推理出错: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, access_log=False)