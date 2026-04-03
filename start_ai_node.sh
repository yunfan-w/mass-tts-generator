#!/bin/bash
#SBATCH --job-name=TTS_Worker
#SBATCH --partition=gpu
#SBATCH --gres=gpu:4             # 要满 4 张卡
#SBATCH --constraint="rtx_2080ti" # ⚡ 明确告诉系统这卡是对的（或者干脆删掉这行）
#SBATCH --cpus-per-task=16       # ai系列有30个CPU，16个完全合法
#SBATCH --mem=50G                # ⚡ 关键保命修改：退一步海阔天空，只申请 50G
#SBATCH --output='slurm_out/worker-%N-%j.out'
#SBATCH --time=4-00:00:00
#SBATCH --mail-type=begin,end
#SBATCH --mail-user=abe6fq@virginia.edu 

module purge
module load gcc cuda miniforge
mamba activate /u/abe6fq/.conda/envs/tts 

# 获取当前跑在哪台机器上
NODE_NAME=$(hostname)
echo "🚀 正在节点 $NODE_NAME 上启动 4 个 TTS 接口..."

PORT=8000
for gpu_id in {0..3}; do
    # 核心：单卡单进程！
    CUDA_VISIBLE_DEVICES=$gpu_id /u/abe6fq/.conda/envs/tts/bin/python /u/abe6fq/tts400/api.py --port $PORT &
    
    echo "[$NODE_NAME - GPU $gpu_id] 端口 $PORT 启动中..."
    PORT=$((PORT + 1))
    sleep 0.5
done

echo "✅ $NODE_NAME 上的 4 个 Worker 已就绪！"

# 这是一个死循环，用来保持 SLURM 任务不退出，直到你手动 cancel
wait