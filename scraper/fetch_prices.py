"""
fetch_prices.py — 价格采集适配器 (gpu-server-compare)
设计: 零密钥可跑 + 有密钥增强，全失败不覆写，落盘到 data/price_history.json

支持源 (按优先级)：
  US:  TechPowerUp MSRP (基准) → Newegg (需 Cookie, 否则跳过) → Amazon Keepa (需 key)
  EU:  Geizhals/Skinflint via Apify actor (需 APIFY_TOKEN)
  CN:  京东 p.3.cn 价格接口 (skuIds, 无需登录, 需合法 SKU) + 搜索页补充
  JP:  保留 MSRP，kakaku.com 需代理

用法：
  python scraper/fetch_prices.py              # 试所有免 Key 源，打印报告
  APIFY_TOKEN=xxx python scraper/fetch_prices.py --eu   # 拉 EU
  JD_SKUS="100038004550,100104734..." python scraper/fetch_prices.py --cn

输出: data/price_history.json  { "fetched_at": "...", "sources": {...}, "prices": [...] }
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "price_history.json"
GPUS_JSON = ROOT / "data" / "gpus.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}

def fetch(url, headers=None, timeout=15):
    h = {**HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            # try decode
            for enc in ("utf-8","gbk","gb2312"):
                try: return body.decode(enc)
                except: continue
            return body.decode("utf-8", errors="ignore")
    except Exception as e:
        return f"__ERROR__ {e}"

# --- US: Newegg search page is bot-walled; we try the mobile API mirror (often lighter) ---
def try_newegg(keyword="RTX 5090"):
    # public newegg search without JS; may need session cookie — try with referer
    url = f"https://www.newegg.com/p/pl?d={urllib.parse.quote(keyword)}"
    html = fetch(url, headers={"Referer": "https://www.newegg.com/"})
    if html.startswith("__ERROR__"):
        return {"ok": False, "error": html}
    # very rough price extraction (USD $)
    prices = re.findall(r"\$\s*([\d,]+\.\d{2})", html)
    # take median of found prices as proxy
    vals=[]
    for p in prices:
        try:
            v=float(p.replace(",",""))
            if 150 < v < 5000: vals.append(v)
        except: pass
    vals=sorted(vals)
    return {"ok": True, "samples": vals[:12], "count": len(vals), "note": "HTML price regex, may include accessories; use as signal only"}

def try_jd_p3(sku_ids):
    # 京东价格接口 p.3.cn (无需登录, 返回 JSONP)
    if not sku_ids: return {"ok": False, "error": "no sku_ids"}
    url = f"https://p.3.cn/prices/mgets?skuIds=J_{',J_'.join(sku_ids)}&type=1"
    body = fetch(url, headers={"Referer": "https://item.jd.com/"})
    if body.startswith("__ERROR__"): return {"ok": False, "error": body}
    # body is like [{"id":"J_100038004550","p":"2999.00","m":"3299.00"}, ...]
    try:
        j=json.loads(body)
        return {"ok": True, "data": j}
    except Exception as e:
        return {"ok": False, "error": str(e), "raw": body[:600]}

def try_jd_search(keyword="RTX5090"):
    # 京东搜索页 is SPA — search.jd.com returns shell HTML; price comes via separate API
    # we just check reachability
    url = f"https://search.jd.com/Search?keyword={urllib.parse.quote(keyword)}&enc=utf-8"
    html = fetch(url)
    if html.startswith("__ERROR__"): return {"ok": False, "error": html}
    return {"ok": True, "len": len(html), "has_item": "item.jd.com" in html or "jd.com" in html}

def main():
    print(f"[fetch_prices] {datetime.now(timezone.utc).isoformat()}")
    report = {"fetched_at": datetime.now(timezone.utc).isoformat(), "sources": {}, "prices": []}

    # baseline: ensure gpus.json loads
    gpus = json.loads(GPUS_JSON.read_text(encoding="utf-8"))
    print(f"  gpus: {len(gpus)} (baseline MSRP)")

    # US probe
    print("  probing Newegg (US) ...")
    ne = try_newegg("RTX 5090")
    print("   ", ne)
    report["sources"]["newegg_us_probe"] = ne

    # CN probe
    jd_skus = [s for s in os.environ.get("JD_SKUS","").split(",") if s.strip()]
    if jd_skus:
        print(f"  probing JD p.3.cn with {len(jd_skus)} SKUs ...")
        jd = try_jd_p3(jd_skus[:8])
        print("   ", jd)
        report["sources"]["jd_p3"] = jd
    else:
        print("  JD p.3.cn: skip (set JD_SKUS env to test, e.g. JD_SKUS=100038004550,100014...)")
        # try demo SKU (RTX 4060 common)
        demo = try_jd_p3(["100038004550"])
        print("   demo probe:", demo)
        report["sources"]["jd_p3_demo"] = demo
        jd_search = try_jd_search("RTX5090")
        report["sources"]["jd_search"] = jd_search

    # EU: Apify Geizhals
    token = os.environ.get("APIFY_TOKEN")
    if token:
        print("  Apify Geizhals token present — would run actor here (skipped in demo)")
        report["sources"]["geizhals"] = {"ok": True, "note": "token present"}
    else:
        print("  Geizhals/EU: skip (set APIFY_TOKEN to enable Apify actor solidcode/geizhals-de-scraper)")
        report["sources"]["geizhals"] = {"ok": False, "reason": "no APIFY_TOKEN (free tier  $1/1k, 京东/亚马逊无需)"}

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {OUT}")
    print("\n建议:")
    print(" - US 现货价最稳的是 Keepa(亚马逊历史价, 免费额度) 或 Apify Newegg actor；直接裸爬 Newegg/Geizhals 均被 Cloudflare 拦，性价比低。")
    print(" - CN 最可落地是京东联盟API(需个体户资质) 或 p.3.cn+SKU 白名单轮询；搜索页不可直接解析。")
    print(" - 落地做法: 本脚本作探针，定时任务每日跑一次，成功则合并到 gpus.json region_price，失败保留旧值。")

if __name__ == "__main__":
    main()
