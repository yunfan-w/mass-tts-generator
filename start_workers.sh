#!/bin/bash
echo "🚀 正在 8 张 A4500 上极速启动 24 个 TTS 并发 Worker..."

# 初始化端口号（用大写保持一致）
PORT=8000

for gpu_id in {0..7}; do
    for worker_id in {1..3}; do
        # 1. 启动进程
        # 注意：这里确保 CUDA_VISIBLE_DEVICES 后面用的是变量 gpu_id
        PYTHONWARNINGS="ignore" CUDA_VISIBLE_DEVICES=$gpu_id nohup python api.py --port $PORT > /dev/null 2>&1 &
        
        echo "[GPU $gpu_id] 端口 $PORT 启动中..."
        
        # 2. 端口号自增
        PORT=$((PORT + 1))
        
        # 3. 稍微停顿一下，防止 CPU 瞬间拉爆
        sleep 0.5
    done
done

echo "------------------------------------------------"
echo "✅ 24 个 Worker 已投递到后台运行！端口范围: 8000 - 8023"
echo "💡 提示：模型加载约需 30 秒，请使用 'nvidia-smi' 观察显存填满后再运行 run_tts.py"
echo "------------------------------------------------"

# 去掉 wait，这样脚本执行完会直接回到命令行界面，方便你下一步运行 run_tts.py