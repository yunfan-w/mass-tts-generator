import asyncio
import aiohttp
import os
import time
import io
import shutil
from nltk.tokenize import sent_tokenize
from pydub import AudioSegment
from tqdm import asyncio as tqdm_asyncio

# ================= 核心配置区 =================
TEXT_FILE = "oneplus_keynote.txt"
FINAL_OUTPUT = "OnePlus_Full_Keynote.wav"
TEMP_PARTS_DIR = "/dev/shm/oneplus_parts"
# 确保启动脚本拉起了 8000-8023 端口
PORTS = [8000 + i for i in range(24)]    
FLUSH_SIZE = 50 # 频繁落盘，降低内存压力
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
    """
    极致抢占模式：每个 Worker 对应一个固定端口
    从队列抢到任务后直接轰炸该端口
    """
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
            # 极致性能：减少重试次数，把时间留给下一个任务
            async with session.post(url, json={"text": chunk}, timeout=180) as resp:
                if resp.status == 200:
                    results[i] = await resp.read()
                    success = True
                else:
                    # 快速重试一次
                    async with session.post(url, json={"text": chunk}, timeout=180) as resp2:
                        if resp2.status == 200:
                            results[i] = await resp2.read()
                            success = True
        except:
            pass
        
        if not success:
            # 暴力兜底：插入1分钟静音，绝不回头
            print(f"\n[🚀 跳过] 第 {i} 段失败，注入静音占位")
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
        
        # 检查批次是否完整
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
            # 推理全部完成后的强制清空逻辑
            if pbar_desc.n == total_chunks:
                await asyncio.sleep(2)
                for m_idx in range(write_ptr, target_end):
                    if m_idx not in results:
                        results[m_idx] = results.get(m_idx-1, b"") 
                continue
            await asyncio.sleep(1) # 高频检查

    return part_files

async def main():
    if os.path.exists(TEMP_PARTS_DIR):
        shutil.rmtree(TEMP_PARTS_DIR)
    os.makedirs(TEMP_PARTS_DIR, exist_ok=True)
    
    with open(TEXT_FILE, "r", encoding="utf-8") as f:
        chunks = safe_chunking(f.read())
    
    total_chunks = len(chunks)
    print(f"🔥 24 路并发全开！目标：10 分钟内干掉 8662 词。")

    queue = asyncio.Queue()
    for i, chunk in enumerate(chunks):
        queue.put_nowait((i, chunk, None))

    start_time = time.time()
    pbar = tqdm_asyncio.tqdm(total=total_chunks, desc="⚡ 生产效率", unit="chunk")
    
    # 彻底解除连接限制
    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 24个协程对应24个端口
        workers = [asyncio.create_task(tts_worker(w, queue, session, pbar)) for w in range(24)]
        flush_task = asyncio.create_task(monitor_and_flush(total_chunks, pbar))
        
        await queue.join()
        for _ in workers: queue.put_nowait(None)
        await asyncio.gather(*workers)
        part_files = await flush_task
    
    pbar.close()

    print(f"\n📦 正在进行最终暴力拼接...")
    final_audio = AudioSegment.empty()
    for pf in sorted(part_files):
        final_audio += AudioSegment.from_file(pf)
    
    final_audio.export(FINAL_OUTPUT, format="wav")
    shutil.rmtree(TEMP_PARTS_DIR)
    
    print(f"🏁 任务大圆满！耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    asyncio.run(main())