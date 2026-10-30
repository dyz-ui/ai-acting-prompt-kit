"""本机 AI 生成能力探测：CUDA 是否可用、显存边界、CPU 算力。

不下载任何模型，只用 torch 做硬件级探测，避免为了测一句话拉几个 G。
"""
import time

import torch


def line(k, v):
    print(f"{k:<22}{v}")


print("=" * 52)
line("torch 版本", torch.__version__)
line("编译时 CUDA", torch.version.cuda)
line("cudnn 版本", torch.backends.cudnn.version())
line("CUDA 可用", torch.cuda.is_available())
line("GPU 数量", torch.cuda.device_count())

if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    line("GPU", p.name)
    line("显存", f"{p.total_memory / 1024**3:.2f} GB")
    line("算力", f"{p.major}.{p.minor}")
    line("SM 数量", p.multi_processor_count)
    for mb in (256, 512, 1024, 1536, 2048, 3072):
        try:
            t = torch.zeros(int(mb * 1024**2 / 4), dtype=torch.float32, device="cuda")
            torch.cuda.synchronize()
            del t
            print(f"  分配 {mb:>5} MB  成功")
        except RuntimeError as e:
            print(f"  分配 {mb:>5} MB  失败：{str(e).splitlines()[0][:70]}")
            break
else:
    print("\n[诊断] CUDA 不可用，逐项排查：")
    try:
        import ctypes

        try:
            ctypes.CDLL("nvcuda.dll")
            print("  nvcuda.dll          可加载")
        except OSError:
            print("  nvcuda.dll          缺失或无法加载  ← 常见根因")
    except Exception as e:  # noqa: BLE001
        print(f"  驱动探测异常：{e}")

print("\n" + "=" * 52)
print("CPU 卷积吞吐（用于估算单帧耗时）")

torch.set_num_threads(torch.get_num_threads())
print(f"  线程数：{torch.get_num_threads()}")

for (h, w, c) in [(64, 64, 320), (128, 128, 128), (256, 256, 64)]:
    x = torch.randn(1, c, h, w)
    conv = torch.nn.Conv2d(c, c, 3, padding=1)
    with torch.no_grad():
        conv(x)  # 预热
        n = 3
        t0 = time.perf_counter()
        for _ in range(n):
            conv(x)
        dt = (time.perf_counter() - t0) / n
    flops = 2 * h * w * c * c * 9
    print(f"  {h}x{w} ch{c:<4} {dt * 1000:8.1f} ms/层   {flops / dt / 1e9:7.1f} GFLOPS")

print("\n参考：SD1.5 单次 UNet 前向约 340 GFLOPs（512x512，社区常用值）")
print("      用上面的 GFLOPS 除一下，就是单帧的纯计算时间下限（还没算采样步数）")
