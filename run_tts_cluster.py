import asyncio
import aiohttp
import os
import time
import io
import shutil
import subprocess
import argparse
from docx import Document
from nltk.tokenize import sent_tokenize
from pydub import AudioSegment
from tqdm import asyncio as tqdm_asyncio

# ================= 核心配置 (分布式集群版) =================
TEMP_BASE_DIR = "/dev/shm/tts_parts"
FLUSH_SIZE = 50 

# 构建跨机 16 节点 URL 矩阵
NODES = ["ai01", "ai02", "ai03", "ai04"]
PORTS = [8000, 8001, 8002, 8003]

WORKER_URLS = []
for node in NODES:
    for port in PORTS:
        # 在集群内网，直接用机器名就能互相通信
        WORKER_URLS.append(f"http://{node}:{port}/api/tts")

# =========================================================
results = {}

def read_docx(file_path):
    doc = Document(file_path)
    full_text = [para.text for para in doc.paragraphs]
    return "\n".join(full_text)

def safe_chunking(text, max_words=30):
    sentences = sent_tokenize(text.replace("\n", " "))
    chunks = []
    for sent in sentences:
        if len(sent.split()) <= max_words:
            chunks.append(sent)
        else:
            sub_sents = sent.split(',')
            for sub in sub_sents:
                if sub.strip(): chunks.append(sub.strip() + ",")
    return chunks

# 注意这里的参数变成了 worker_url
async def tts_worker(worker_url, queue, session, pbar):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        i, chunk, _ = item 
        success = False
        
        # ⚡ 核心升级 1：加入 3 次重试机制 (治本)
        for attempt in range(3):
            try:
                # 尝试向节点发送请求
                async with session.post(worker_url, json={"text": chunk}, timeout=180) as resp:
                    if resp.status == 200:
                        results[i] = await resp.read()
                        success = True
                        break  # ✅ 成功拿到音频，直接跳出重试循环
                    else:
                        print(f"\n⚠️ 节点 {worker_url} 返回状态码 {resp.status}，准备重试...")
            except Exception as e:
                pass # 遇到超时或断连，不报错，继续走下面的重试逻辑
            
            # 如果没成功，休息 2 秒钟再试下一次，给 GPU 一点喘息时间
            await asyncio.sleep(2)
        
        # ⚡ 核心升级 2：如果 3 次都头铁失败了，才插入 3 秒短静默 (治标)
        if not success:
            print(f"\n❌ 警告: 文本块 [{i}] 连续 3 次生成失败，已插入 5 秒静默占位。")
            silent_segment = AudioSegment.silent(duration=5000, frame_rate=24000)
            buf = io.BytesIO()
            silent_segment.export(buf, format="wav")
            results[i] = buf.getvalue()
            
        pbar.update(1)
        queue.task_done()

async def monitor_and_flush(total_chunks, pbar_desc, temp_dir):
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
            part_path = os.path.join(temp_dir, f"part_{part_idx:04d}.wav")
            batch_audio.export(part_path, format="wav")
            part_files.append(part_path)
            write_ptr = target_end; part_idx += 1
        else:
            if pbar_desc.n == total_chunks:
                await asyncio.sleep(2)
                for m_idx in range(write_ptr, target_end):
                    if m_idx not in results: results[m_idx] = results.get(m_idx-1, b"") 
                continue
            await asyncio.sleep(1)
    return part_files

async def main(input_file, output_file):
    task_id = os.path.basename(input_file).replace(" ", "_")
    temp_dir = os.path.join(TEMP_BASE_DIR, task_id)
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    text = read_docx(input_file)
    chunks = safe_chunking(text)
    total_chunks = len(chunks)
    
    print(f"🚀正在处理: {os.path.basename(input_file)} (共 {total_chunks} 段)")
    print(f"正在通过局域网向 16 个分布式节点分发任务...")
    
    queue = asyncio.Queue()
    for i, chunk in enumerate(chunks):
        queue.put_nowait((i, chunk, None))

    pbar = tqdm_asyncio.tqdm(total=total_chunks, desc="生成进度", unit="chunk", disable=True)
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        # ⚡ 核心并发派发：遍历 16 个 URL，创建 16 个并行的协程 Worker！
        workers = [asyncio.create_task(tts_worker(url, queue, session, pbar)) for url in WORKER_URLS]
        flush_task = asyncio.create_task(monitor_and_flush(total_chunks, pbar, temp_dir))
        
        await queue.join()
        for _ in workers: queue.put_nowait(None)
        await asyncio.gather(*workers)
        part_files = await flush_task
    pbar.close()

    list_file = os.path.join(temp_dir, "filelist.txt")
    with open(list_file, "w") as f:
        for pf in sorted(part_files): f.write(f"file '{os.path.abspath(pf)}'\n")
    
    temp_wav = output_file.replace(".mp3", ".wav")
    # subprocess.run(f"ffmpeg -f concat -safe 0 -i {list_file} -c copy {temp_wav} -y", shell=True, check=True, capture_output=True)
    # subprocess.run(f"ffmpeg -i {temp_wav} -codec:a libmp3lame -qscale:a 2 {output_file} -y", shell=True, check=True, capture_output=True)

    subprocess.run(f'ffmpeg -f concat -safe 0 -i "{list_file}" -c copy "{temp_wav}" -y', shell=True, check=True, capture_output=True)
    subprocess.run(f'ffmpeg -i "{temp_wav}" -codec:a libmp3lame -qscale:a 2 "{output_file}" -y', shell=True, check=True, capture_output=True)
    
    # ⚡ 加入 atempo 音频滤镜，0.85 就是放慢 15%，1.2 就是加快 20%
    # subprocess.run(f'ffmpeg -i "{temp_wav}" -filter:a "atempo=0.9" -codec:a libmp3lame -qscale:a 2 "{output_file}" -y', shell=True, check=True, capture_output=True)
    
    if os.path.exists(temp_wav): os.remove(temp_wav)
    shutil.rmtree(temp_dir)
    print(f"✅完成: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    asyncio.run(main(args.input, args.output))