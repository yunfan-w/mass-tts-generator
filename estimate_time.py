import os
from docx import Document

# 目标文件夹
SRC_DIR = "/u/abe6fq/tts400/Transcript"

# 你的基准测试数据（Benchmark）
BENCHMARK_WORDS = 4456      #1025词
BENCHMARK_SECONDS = 600      # 135秒

def count_chars(file_path):
    try:
        doc = Document(file_path)
        # 将所有段落拼接，并剔除空格、换行等不发音的空白符，还原最真实的TTS字数
        text = "".join([para.text for para in doc.paragraphs])
        text = text.replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
        return len(text)
    except Exception as e:
        print(f"⚠️ 读取文件失败 {file_path}: {e}")
        return 0

def main():
    print(f"🔍 正在扫描目录: {SRC_DIR} ...")
    total_words = 0
    file_count = 0
    
    # 遍历所有子文件夹
    for root, dirs, files in os.walk(SRC_DIR):
        for file in files:
            # 识别 docx 文件，同时跳过 Word 打开时产生的隐藏缓存文件(以~$开头)
            if file.endswith(".docx") and not file.startswith("~"):
                file_path = os.path.join(root, file)
                count = count_chars(file_path)
                total_words += count
                file_count += 1
                
    print(f"✅ 扫描完毕！共统计了 {file_count} 个文档。")
    print(f"📊 总字数（纯净字符数）：{total_words} 字")
    
    # 核心计算逻辑
    speed = BENCHMARK_WORDS / BENCHMARK_SECONDS
    total_seconds = total_words / speed
    
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    
    print("=" * 45)
    print(f"⚡ 集群当前吞吐量：{speed:.2f} 字/秒 (16卡并发)")
    print(f"⏳ 预计生成所有音频的总耗时：大约 {hours} 小时 {minutes} 分钟")
    print("=" * 45)

if __name__ == "__main__":
    main()