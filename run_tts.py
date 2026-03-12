import asyncio
import aiohttp
import os
import time
import io
import shutil
import subprocess
from nltk.tokenize import sent_tokenize
from pydub import AudioSegment
from tqdm import asyncio as tqdm_asyncio

# ================= 核心配置区 =================
TEXT_FILE = "oneplus_keynote.txt"
FINAL_WAV = "OnePlus_Full_Keynote.wav"
FINAL_MP3 = "OnePlus_Full_Keynote.mp3"  # 最终输出 MP3
TEMP_PARTS_DIR = "/dev/shm/oneplus_parts"
PORTS = [8000 + i for i in range(24)]    
FLUSH_SIZE = 50 
# ==============================================

results = {}

def safe_chunking(text, max_words=30):
    sentences = sent_tokenize(text.replace("\n", " "))
    chunks = []
    for sent in sentences:
        if len(sent.split()) <= max_words:
            chunks.append(sent)
        else:
            sub_sents = sent.split(',')
            for sub in sub_sents:
                if sub.strip():
                    chunks.append(sub.strip() + ",")
    return chunks

async def tts_worker(worker_id, queue, session, pbar):
    port = PORTS[worker_id]
    url = f"http://127.0.0.1:{port}/api/tts"
    
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
            
        i, chunk, _ = item 
        success = False
        
        try:
            async with session.post(url, json={"text": chunk}, timeout=180) as resp:
                if resp.status == 200:
                    results[i] = await resp.read()
                    success = True
        except:
            pass
        
        if not success:
            # 插入 1 分钟静音占位
            print(f"\n[🚀 跳过] 第 {i} 段失败，注入 60s 静音")
            silent_segment = AudioSegment.silent(duration=60000, frame_rate=24000)
            buf = io.BytesIO()
            silent_segment.export(buf, format="wav")
            results[i] = buf.getvalue()
            
        pbar.update(1)
        queue.task_done()

async def monitor_and_flush(total_chunks, pbar_desc):
    write_ptr = 0
    part_idx = 0
    part_files = []
    
    while write_ptr < total_chunks:
        target_end = min(write_ptr + FLUSH_SIZE, total_chunks)
        if all(idx in results for idx in range(write_ptr, target_end)):
            batch_audio = AudioSegment.empty()
            for idx in range(write_ptr, target_end):
                audio_bytes = results.pop(idx)
                segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
                batch_audio += segment
            
            part_path = os.path.join(TEMP_PARTS_DIR, f"part_{part_idx:04d}.wav")
            batch_audio.export(part_path, format="wav")
            part_files.append(part_path)
            write_ptr = target_end
            part_idx += 1
        else:
            if pbar_desc.n == total_chunks:
                await asyncio.sleep(2)
                for m_idx in range(write_ptr, target_end):
                    if m_idx not in results:
                        results[m_idx] = results.get(m_idx-1, b"") 
                continue
            await asyncio.sleep(1)
    return part_files

async def main():
    if os.path.exists(TEMP_PARTS_DIR):
        shutil.rmtree(TEMP_PARTS_DIR)
    os.makedirs(TEMP_PARTS_DIR, exist_ok=True)
    
    with open(TEXT_FILE, "r", encoding="utf-8") as f:
        chunks = safe_chunking(f.read())
    
    total_chunks = len(chunks)
    print(f"🔥 24路并发 + FFmpeg 后期流水线启动！")

    queue = asyncio.Queue()
    for i, chunk in enumerate(chunks):
        queue.put_nowait((i, chunk, None))

    start_time = time.time()
    pbar = tqdm_asyncio.tqdm(total=total_chunks, desc="⚡ 生成进度", unit="chunk")
    
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [asyncio.create_task(tts_worker(w, queue, session, pbar)) for w in range(len(PORTS))]
        flush_task = asyncio.create_task(monitor_and_flush(total_chunks, pbar))
        
        await queue.join()
        for _ in workers: queue.put_nowait(None)
        await asyncio.gather(*workers)
        part_files = await flush_task
    
    pbar.close()

    # --- FFmpeg 高速拼接环节 ---
    print(f"\n📦 正在使用 FFmpeg 拼接 WAV...")
    list_file = os.path.join(TEMP_PARTS_DIR, "filelist.txt")
    with open(list_file, "w") as f:
        for pf in sorted(part_files):
            f.write(f"file '{os.path.abspath(pf)}'\n")
    
    # 拼接 WAV (不重新编码，瞬间完成)
    concat_cmd = f"ffmpeg -f concat -safe 0 -i {list_file} -c copy {FINAL_WAV} -y"
    subprocess.run(concat_cmd, shell=True, check=True)

    # --- FFmpeg 转码 MP3 环节 ---
    print(f"🎵 正在转码为 MP3 (192kbps)...")
    mp3_cmd = f"ffmpeg -i {FINAL_WAV} -codec:a libmp3lame -qscale:a 2 {FINAL_MP3} -y"
    subprocess.run(mp3_cmd, shell=True, check=True)

    # --- 确认文件存在后清理 ---
    if os.path.exists(FINAL_MP3):
        print(f"\n✨ 检测到 MP3 已生成，清理内存碎片...")
        shutil.rmtree(TEMP_PARTS_DIR)
    
    elapsed = time.time() - start_time
    print(f"\n🎉 任务大圆满！")
    print(f"⚡ 总耗时: {elapsed:.2f} 秒")
    print(f"📁 最终成品: {os.path.abspath(FINAL_MP3)}")

if __name__ == "__main__":
    asyncio.run(main())