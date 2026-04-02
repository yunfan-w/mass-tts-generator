#!/bin/bash
#SBATCH --job-name=TTS_Full
#SBATCH --partition=gpu
#SBATCH --gres=gpu:4             
#SBATCH --constraint="rtx_4000"     
#SBATCH --cpus-per-task=28       
#SBATCH --mem=500G               
#SBATCH --output='slurm_out/tts-%j.out'
#SBATCH --time=2-00:00:00        # 给足 48 小时，确保 240 小时的音频能从容跑完

module purge
module load gcc cuda miniforge
conda activate /u/abe6fq/.conda/envs/tts

PORT=8000
for gpu_id in {0..3}; do
    for worker_id in {1..3}; do
        # 核心：绑定 GPU、忽略警告、吃掉海量冗余日志、放入后台
        PYTHONWARNINGS="ignore" CUDA_VISIBLE_DEVICES=$gpu_id nohup python /u/abe6fq/mla/api.py --port $PORT > /dev/null 2>&1 &
        
        echo "[GPU $gpu_id] 端口 $PORT 启动中..."
        PORT=$((PORT + 1))
        sleep 0.5
    done
done

echo "------------------------------------------------"
echo "✅ 24 个 Worker 已投递到后台运行！端口范围: 8000 - 8023"
echo "⏳ 等待 3 分钟让显存预热，模型完全加载..."
echo "------------------------------------------------"
sleep 180

# --- 2. 遍历文件夹并执行任务 ---
GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1 | awk '{print $NF}' | tr '[:upper:]' '[:lower:]')
SRC_DIR="/u/abe6fq/tts400/Transcript"
DEST_DIR="/u/abe6fq/tts400/Audio_${GPU_MODEL}"

# 查找所有 docx 文件（处理带空格的文件名）
find "$SRC_DIR" -name "*.docx" | while read -r docx_path
do
    # 计算相对路径，保持文件夹结构
    relative_path=${docx_path#$SRC_DIR/}
    output_path="$DEST_DIR/${relative_path%.docx}.mp3"
    
    echo "🎵 处理中: $relative_path"
    # 运行刚才改造的 Python 脚本
    python /u/abe6fq/tts400/run_tts.py --input "$docx_path" --output "$output_path"
done

# --- 3. 任务结束，清理后端 ---
echo "🧹 任务完成，清理后端进程..."
pkill -u abe6fq -f "api.py"

conda deactivate
echo "🎉 全量任务大圆满！"