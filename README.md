# 🏭 TTS-Pipeline-Pro: Industrial-Scale Asynchronous TTS Generator

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![CUDA 12.8](https://img.shields.io/badge/CUDA-12.8-green.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Turbo-orange.svg)
![Architecture](https://img.shields.io/badge/Architecture-Distributed%20Workers-red.svg)

[中文版介绍请见下方 (Chinese Version Below)](#-中文介绍-chinese-version)

## 📖 Project Overview
TTS-Pipeline-Pro is a high-throughput, fault-tolerant Text-to-Speech (TTS) generation pipeline designed for massive audio production. Originally built to handle a 240-hour audio generation challenge (~960,000 words), it utilizes a preemptive Producer-Consumer architecture to maximize GPU utilization across multiple nodes.

## ✨ Key Features
* **Dynamic Preemptive Scheduling**: Uses an `asyncio.Queue` to dispatch tasks dynamically. Workers process tasks as soon as they are free, ensuring 100% utilization across all GPUs without bottlenecking on slow chunks.
* **Fault-Tolerant Fallback**: Implements a strict fail-safe mechanism. If a text chunk repeatedly fails to generate, the system automatically injects a 60-second silent placeholder, guaranteeing that the pipeline never hangs and output sequence remains intact.
* **Memory-Safe Flushing**: Audio segments are merged and flushed to the `/dev/shm` (RAM disk) in batches (e.g., every 50 chunks), keeping Python memory footprint extremely low even during hours of continuous inference.
* **FFmpeg Turbo Concatenation**: Bypasses the exponentially slow memory-copy issues of native audio libraries by using FFmpeg's binary stream copy (`-c copy`) for instant concatenation, followed by automated MP3 192kbps encoding.

## 🚀 Hardware & Performance (Tested)
* **Hardware**: 8x NVIDIA RTX A4500 (20GB VRAM)
* **Concurrency**: 24 Workers (3 processes per GPU)
* **Performance Benchmark**: Generated 130 minutes of audio (8,662 words) in **800 seconds**.
* **Real-Time Factor (RTF)**: ~9.77x
* **240-Hour Projection**: Estimated 24.5 hours of continuous processing for 14,400 minutes of audio.



---

# 🇨🇳 中文介绍 (Chinese Version)

## 📖 项目简介
TTS-Pipeline-Pro 是一个专为超大规模音频生产打造的**高吞吐、强容错**文本转语音（TTS）工业级流水线。该项目起初为应对“240小时（约96万词）连续音频生成”挑战而设计，通过抢占式“生产者-消费者”架构，将多 GPU 矩阵的算力压榨到极致。

## ✨ 核心特性
* **动态抢占式调度**：摒弃死板的顺序分配，通过全局异步队列（`asyncio.Queue`）派发任务。24个并行 Worker 谁空闲谁接单，彻底消除长难句带来的“木桶效应”，实现 8 卡负载绝对均衡。
* **硬核容错兜底机制**：针对长篇推理中难以避免的偶发崩溃，设计了断腕级容错：单段推理多次失败后，系统会强行注入 60 秒的静音占位符，确保主进程永不卡死，最终合并时序严丝合缝。
* **内存安全级固化（OOM防护）**：每完成 50 个短句，系统立即将其在内存中拼接并写入 `/dev/shm`（极速内存盘），同时释放 Python 对象。连续运行几天几夜也不会发生内存泄漏。
* **FFmpeg 极速合并流水线**：抛弃原生音频库（如 Pydub）在处理数小时音频时带来的指数级内存暴涨问题，直接调用系统级 FFmpeg 的二进制流拷贝机制，瞬间完成成百上千个音频碎片的拼接，并自动转码为高品质 MP3。

## 🚀 硬件与实测性能
* **运行环境**: 8x NVIDIA RTX A4500 (20GB 显存)
* **并发规模**: 24 路并发 (单卡承载 3 个 Worker)
* **实测速度**: 800 秒内生成 130 分钟音频（8,662字讲稿）。
* **加速比**: 约 10 倍于人类正常语速。
* **240小时极限推演**: 跑完全量 240 小时（14,400分钟）音频，预计仅需 **24.5 小时**。

## 🛠️ Roadmap (240h Challenge)
- [x] Multi-GPU environment initialization
- [x] Dynamic load balancing & memory flush
- [x] FFmpeg integration & error fallback
- [ ] Chunking & batching for 1-million-word dataset
- [ ] Checkpoint system (Resume from failure)