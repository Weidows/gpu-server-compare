"""
GPU / 价格数据爬虫 — gpu-server-compare
纯标准库 + 可选依赖 (requests, beautifulsoup4)

用法:
  python scraper/fetch_gpus.py              # 增量更新 data/gpus.json
  python scraper/fetch_gpus.py --force      # 全量重爬
  python scraper/fetch_prices.py            # 刷新价格

数据源:
  1. TechPowerUp GPU Database — https://www.techpowerup.com/gpu-specs/
     提供规格、发布时间、制程、TDP 等 (HTML 解析, 无官方 API)
  2. Geizhals / Newegg 价格 (可选, 需反爬容错)
  3. 本地 data/gpus.json 作为真源, 爬虫只更新缺失/过期字段

设计原则: 失败不覆写已有数据, 打印可读日志, 单文件可跑
"""
import json, re, time, sys, os
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).parent.parent
DATA_JSON = ROOT / "data" / "gpus.json"
HEADERS = {"User-Agent": "gpu-server-compare/1.0 (+https://github.com/Weidows)"}

# 要爬的 TechPowerUp 规格页 slug
TARGET_GPUS = [
    "geforce-rtx-5090", "geforce-rtx-5080", "geforce-rtx-5070-ti",
    "geforce-rtx-4090", "geforce-rtx-4080-super", "geforce-rtx-4070-super",
    "radeon-rx-7900-xtx", "radeon-rx-7900-xt", "radeon-rx-9070-xt", "radeon-rx-9070",
    "radeon-rx-7800-xt", "arc-b580",
    "h100-pcie", "h100-tensor-core", "l40s", "rtx-6000-ada-generation",
    "instinct-mi300x", "instinct-mi325x",
]

TPU_BASE = "https://www.techpowerup.com/gpu-specs"

def fetch_html(url, retries=3):
    for i in range(retries):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", errors="ignore")
        except (HTTPError, URLError) as e:
            print(f"  [retry {i+1}/{retries}] {url} -> {e}")
            time.sleep(2*(i+1))
    return None

def parse_specs(html):
    """从 TPU 详情页提取关键字段, 返回 dict"""
    if not html:
        return {}
    out = {}
    # 常见字段: Release Date, TDP, Memory Size, Bandwidth, Process, Transistors...
    patterns = {
        "release": r"Released</dt>\s*<dd[^>]*>([^<]+)",
        "tdp": r"TDP</dt>\s*<dd[^>]*>([\d,\.]+)\s*W",
        "vram": r"Memory Size</dt>\s*<dd[^>]*>([\d]+)\s*GB",
        "bandwidth": r"Bandwidth</dt>\s*<dd[^>]*>([\d,\.]+)\s*GB/s",
        "process": r"Process Size</dt>\s*<dd[^>]*>([^<]+)",
        "bus": r"Memory Bus</dt>\s*<dd[^>]*>([\d]+)\s*bit",
        "base_clock": r"GPU Clock</dt>\s*<dd[^>]*>([\d]+)\s*MHz",
        "boost_clock": r"Boost Clock</dt>\s*<dd[^>]*>([\d]+)\s*MHz",
    }
    for k, pat in patterns.items():
        m = re.search(pat, html, re.I)
        if m:
            out[k] = m.group(1).strip()
    return out

def main():
    force = "--force" in sys.argv
    print(f"[fetch_gpus] {datetime.now(timezone.utc).isoformat()}  force={force}")
    # 读现有数据
    existing = []
    if DATA_JSON.exists():
        existing = json.loads(DATA_JSON.read_text(encoding="utf-8"))
        print(f"  existing: {len(existing)} entries")
    id_map = {g["id"]: g for g in existing}

    updated = 0
    for slug in TARGET_GPUS:
        url = f"{TPU_BASE}/{slug}.shtml"
        print(f"  fetching {slug} ...", end=" ")
        html = fetch_html(url)
        if not html:
            print("FAILED (skip)")
            continue
        specs = parse_specs(html)
        if specs:
            print(f"OK {specs}")
        else:
            print("parsed empty (page structure changed?)")
        # 这里仅打印, 不自动覆写 — 人工确认后再写入
        time.sleep(1.2)

    print(f"\n[done] checked {len(TARGET_GPUS)} pages.")
    print("  提示: 本脚本为增量辅助, 正式数据仍以 data/gpus.json 人工校验版为准。")
    print("  如需自动合并, 加 --apply 才会写回文件 (当前未实现, 避免误覆写)。")

if __name__ == "__main__":
    main()
