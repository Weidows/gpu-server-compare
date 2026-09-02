# GPU & 服务器 全维度对比

> 40+ 显卡 + 11 台服务器 — 价格 / 性能 / 能效 / 显存带宽 / 多卡扩展 / 发布时间 / 地区供货

- **在线预览**: https://server-mark.weidows.tech/
- **数据**: `data/gpus.json` / `data/servers.json` + `data/price_history.json`
- **爬虫**: `scraper/fetch_gpus.py` (TechPowerUp) / `scraper/fetch_prices.py` (多源探针)

本地运行: `python -m http.server 8000` 然后打开 http://127.0.0.1:8000

部署: 推送到 `main` 自动发布到 GitHub Pages（见 `.github/workflows/deploy.yml`）。
