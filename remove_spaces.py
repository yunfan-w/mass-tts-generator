import os

# 你的源文件夹路径
SRC_DIR = "/u/abe6fq/tts400/Transcript"

def remove_spaces_from_filenames():
    print(f"🔍 开始扫描并清理目录: {SRC_DIR} ...")
    rename_count = 0
    
    # 遍历所有子目录和文件
    for root, dirs, files in os.walk(SRC_DIR):
        for filename in files:
            # 如果文件名中包含空格
            if " " in filename:
                old_path = os.path.join(root, filename)
                
                # 将空格全部替换为空（直接删除）
                new_filename = filename.replace(" ", "")
                new_path = os.path.join(root, new_filename)
                
                try:
                    # 如果重命名后的文件不存在，则安全重命名
                    if not os.path.exists(new_path):
                        os.rename(old_path, new_path)
                        print(f"✅ 净化成功: '{filename}' -> '{new_filename}'")
                        rename_count += 1
                    else:
                        print(f"⚠️ 跳过: 目标文件 '{new_filename}' 已存在。")
                except Exception as e:
                    print(f"❌ 重命名 '{filename}' 失败: {e}")

    print("=" * 50)
    print(f"🎉 清理完毕！共成功去除了 {rename_count} 个文件名中的空格。")

if __name__ == "__main__":
    remove_spaces_from_filenames()