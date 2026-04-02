import asyncio
import aiohttp
import os
import time
import io
import shutil
import subprocess
import argparse
from docx import Document  # 新增：处理 Word
from nltk.tokenize import sent_tokenize
from pydub import AudioSegment
from tqdm import asyncio as tqdm_asyncio

# ================= 核心配置 =================
TEMP_BASE_DIR = "/dev/shm/tts_parts" # 建议放在内存盘
PORTS = [8000 + i for i in range(24)]    
FLUSH_SIZE = 50 

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
        except: pass
        
        if not success:
            silent_segment = AudioSegment.silent(duration=60000, frame_rate=24000)
            buf = io.BytesIO(); silent_segment.export(buf, format="wav")
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
    # 为当前任务创建独立的临时目录，防止并行冲突
    task_id = os.path.basename(input_file).replace(" ", "_")
    temp_dir = os.path.join(TEMP_BASE_DIR, task_id)
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    # 支持 docx 读取
    text = read_docx(input_file)
    chunks = safe_chunking(text)
    total_chunks = len(chunks)
    
    print(f"🚀 正在处理: {os.path.basename(input_file)} (共 {total_chunks} 段)")
    
    queue = asyncio.Queue()
    for i, chunk in enumerate(chunks):
        queue.put_nowait((i, chunk, None))

    pbar = tqdm_asyncio.tqdm(total=total_chunks, desc="⚡ 生成进度", unit="chunk")
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [asyncio.create_task(tts_worker(w, queue, session, pbar)) for w in range(len(PORTS))]
        flush_task = asyncio.create_task(monitor_and_flush(total_chunks, pbar, temp_dir))
        await queue.join()
        for _ in workers: queue.put_nowait(None)
        await asyncio.gather(*workers)
        part_files = await flush_task
    pbar.close()

    # FFmpeg 拼接和转码
    list_file = os.path.join(temp_dir, "filelist.txt")
    with open(list_file, "w") as f:
        for pf in sorted(part_files): f.write(f"file '{os.path.abspath(pf)}'\n")
    
    temp_wav = output_file.replace(".mp3", ".wav")
    subprocess.run(f"ffmpeg -f concat -safe 0 -i {list_file} -c copy {temp_wav} -y", shell=True, check=True, capture_output=True)
    subprocess.run(f"ffmpeg -i {temp_wav} -codec:a libmp3lame -qscale:a 2 {output_file} -y", shell=True, check=True, capture_output=True)
    
    if os.path.exists(temp_wav): os.remove(temp_wav)
    shutil.rmtree(temp_dir)
    print(f"✅ 完成: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    asyncio.run(main(args.input, args.output))