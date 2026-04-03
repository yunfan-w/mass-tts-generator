#!/bin/bash
#SBATCH --job-name=TTS_Master_Dispatcher
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=200G
#SBATCH --output='slurm_out/master_dispatcher-%j.out'
#SBATCH --time=4-00:00:00
#SBATCH --mail-type=begin,end
#SBATCH --mail-user=abe6fq@virginia.edu 

module purge
module load gcc miniforge

# 强行把 conda tts 环境的 bin 目录塞进系统的全局变量
export PATH="/u/abe6fq/.conda/envs/tts/bin:$PATH"

SRC_DIR="/u/abe6fq/tts400/Transcript"
DEST_DIR="/bigtemp/abe6fq/Audio/"

echo "[中央指挥部] 开始按目录顺序执行全量调度..."

# 第一层循环：遍历 Transcript 下的所有子文件夹 (比如 中国村落5h15min, 资本的故事S2...)
for category_dir in "$SRC_DIR"/*/; do
    
    # 提取当前文件夹的名字 (比如 中国村落5h15min)
    category_name=$(basename "$category_dir")
    echo "=================================================="
    echo "📂 开始处理系列: $category_name"
    echo "=================================================="

    # 第二层循环：遍历当前子文件夹下的所有 .docx 文件
    for docx_path in "$category_dir"*.docx; do
        
        # 提取文件名 (比如 第一集如画.docx)
        file_name=$(basename "$docx_path")
        
        # 拼接出相对路径和输出路径
        relative_path="$category_name/$file_name"
        output_path="$DEST_DIR/${relative_path%.docx}.mp3"
        
        echo "--------------------------------------------------"
        echo "🎬正在派发任务: $relative_path"
        python /u/abe6fq/tts400/run_tts_cluster.py --input "$docx_path" --output "$output_path"
        
    done
done

echo "🎉 全量任务调度彻底完毕！"