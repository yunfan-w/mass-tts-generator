import asyncio
import aiohttp
import os
import time
import io
import shutil
from nltk.tokenize import sent_tokenize
from pydub import AudioSegment
from tqdm import asyncio as tqdm_asyncio # 异步进度条

# ================= 核心配置区 =================
TEXT_FILE = "oneplus_keynote.txt"        # 输入讲稿
FINAL_OUTPUT = "OnePlus_Full_Keynote.wav" # 最终成品文件名
TEMP_PARTS_DIR = "/dev/shm/oneplus_parts" # 临时目录，建议用 /dev/shm (内存盘) 极速读写
PORTS = [8000 + i for i in range(24)]    # 24个后端端口
# PORTS = [7000]    
FLUSH_SIZE = 100                          # 每100段固化一次成一个part文件
# FLUSH_SIZE = 5                          # 每100段固化一次成一个part文件
# ==============================================

results = {}

def safe_chunking(text, max_words=30):
    """英文智能切句：防止单词过多导致模型幻读崩溃"""
    sentences = sent_tokenize(text.replace("\n", " "))
    chunks = []
    for sent in sentences:
        if len(sent.split()) <= max_words:
            chunks.append(sent)
        else:
            # 遇到超长句子，按逗号切分
            sub_sents = sent.split(',')
            for sub in sub_sents:
                if sub.strip():
                    chunks.append(sub.strip() + ",")
    return chunks

async def tts_worker(worker_id, queue, session, pbar):
    """从队列取任务并发送给 24 个后端"""
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
            
        i, chunk, port = item
        url = f"http://127.0.0.1:{port}/api/tts"
        payload = {"text": chunk}
        
        try:
            # 增加重试机制
            success = False
            for retry in range(3):
                try:
                    async with session.post(url, json=payload, timeout=120) as resp:
                        if resp.status == 200:
                            results[i] = await resp.read()
                            success = True
                            break
                        else:
                            await asyncio.sleep(1)
                except Exception:
                    await asyncio.sleep(1)
            
            if not success:
                print(f"\n[!] 警告：第 {i} 段在尝试 3 次后依然失败，跳过。")
        finally:
            pbar.update(1)
            queue.task_done()

async def monitor_and_flush(total_chunks, pbar_desc):
    """后台监控：每当100段到齐，立即拼接成一个part文件落盘，并清空内存"""
    write_ptr = 0
    part_idx = 0
    part_files = []
    
    while write_ptr < total_chunks:
        target_end = min(write_ptr + FLUSH_SIZE, total_chunks)
        
        # 检查 [write_ptr, target_end) 这一区间是否全部下载完成
        if all(idx in results for idx in range(write_ptr, target_end)):
            # 在内存中合并这 100 段
            batch_audio = AudioSegment.empty()
            for idx in range(write_ptr, target_end):
                # 用 .pop() 确保音频数据离开内存，防止 OOM
                audio_bytes = results.pop(idx)
                segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
                batch_audio += segment
            
            # 写入一个独立的 part 文件
            part_path = os.path.join(TEMP_PARTS_DIR, f"part_{part_idx:04d}.wav")
            batch_audio.export(part_path, format="wav")
            part_files.append(part_path)
            
            # print(f"\n[已固化] Part {part_idx} (Index {write_ptr}-{target_end}) 落盘成功")
            write_ptr = target_end
            part_idx += 1
        else:
            # 没到齐，等 2 秒再看
            await asyncio.sleep(2)
            
        # 如果队列任务全部结束（通过pbar判断），但最后几段不足FLUSH_SIZE，也要强行刷出
        if write_ptr < total_chunks and pbar_desc.n == total_chunks:
            # 等待极短时间确保字典填充
            await asyncio.sleep(1)
            continue

    return part_files

async def main():
    # 1. 初始化临时目录
    if os.path.exists(TEMP_PARTS_DIR):
        shutil.rmtree(TEMP_PARTS_DIR)
    os.makedirs(TEMP_PARTS_DIR, exist_ok=True)
    
    # 2. 读取并分段
    print("1. 正在解析一加发布会讲稿...")
    with open(TEXT_FILE, "r", encoding="utf-8") as f:
        chunks = safe_chunking(f.read())
    
    total_chunks = len(chunks)
    print(f"🚀 解析完成：共 {total_chunks} 个短句。开始大规模并发推理...")

    queue = asyncio.Queue()
    for i, chunk in enumerate(chunks):
        queue.put_nowait((i, chunk, PORTS[i % len(PORTS)]))

    # 3. 启动进度条和并发任务
    start_time = time.time()
    pbar = tqdm_asyncio.tqdm(total=total_chunks, desc="生成进度", unit="chunk")
    
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 启动 48 个协程抢占 24 个后端
        workers = [asyncio.create_task(tts_worker(w, queue, session, pbar)) for w in range(48)]
        
        # 启动后台持久化任务
        flush_task = asyncio.create_task(monitor_and_flush(total_chunks, pbar))
        
        # 等待所有推理完成
        await queue.join()
        for _ in workers: queue.put_nowait(None)
        await asyncio.gather(*workers)
        
        # 等待最后一段固化完成
        part_files = await flush_task
    
    pbar.close()

    # 4. 最终无缝拼接
    print(f"\n🏁 推理全部完成，正在合并 {len(part_files)} 个大片段...")
    final_audio = AudioSegment.empty()
    for pf in sorted(part_files): # 确保按文件名顺序合并
        final_audio += AudioSegment.from_file(pf)
    
    print(f"💾 正在导出最终成品：{FINAL_OUTPUT} ...")
    final_audio.export(FINAL_OUTPUT, format="wav")
    
    # 清理现场
    shutil.rmtree(TEMP_PARTS_DIR)
    
    elapsed = time.time() - start_time
    print(f"\n🎉 任务大圆满！")
    print(f"⚡ 总耗时: {elapsed:.2f} 秒 (约 {elapsed/60:.2f} 分钟)")
    print(f"📁 最终成品: {os.path.abspath(FINAL_OUTPUT)}")

if __name__ == "__main__":
    asyncio.run(main())