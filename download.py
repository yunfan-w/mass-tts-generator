from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base", 
    local_dir="./Qwen3-TTS-12Hz-1.7B-Base"
)