# iios 纯协议每日签到

本地 WASM 加解密 + `urllib` 裸 HTTP，**不打开浏览器**。

## 依赖

- Python 3.11+
- Node.js 18+（运行 `crypto/wasm_crypto.cjs`）

## 配置

```powershell
$env:IIOS_USERNAME="you@example.com"
$env:IIOS_PASSWORD="secret"
# 可选
$env:IIOS_BASE_URL="https://www.iios.fun"   # 或 https://www.iios.me
$env:IIOS_WEBAPP="true"                     # 默认 true；false 则普通 1 积分
$env:IIOS_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7.5 Mobile/15E148 Safari/604.1"
```

也可复制 `.env.example` 自行导出变量。

## 运行

```powershell
cd C:\Users\tymol\Desktop\github\sing

python iios_signin.py --selftest      # 加密 + 首页探测
python iios_signin.py --dry-run       # 登录 + 查任务，不签到
python iios_signin.py --no-dry-run         # 真实签到（默认 webapp=true）
python iios_signin.py --no-dry-run --no-webapp   # 强制 webapp=false
```

日志 JSON 中 `result`：

| 值 | 含义 |
|----|------|
| `already_signed` | 今日已签 |
| `dry_run_ready` | dry-run 通过，尚未提交 |
| `signed_now` | 本次签到成功 |

## 目录

```
crypto/                 # WASM + glue（必需）
  wasm_crypto.cjs
  main.*.js
  web_wasm_bg.*.wasm
iios_signin.py          # 入口
.github/workflows/      # 可选定时任务
```

## GitHub Actions

Secrets：`IIOS_USERNAME`、`IIOS_PASSWORD`  
可选 Variables：`IIOS_BASE_URL`、`IIOS_WEBAPP`  

工作流：`.github/workflows/signin.yml`（定时 + 手动），只装 Python/Node。

## 协议要点

- `POST /api/user/login` → JWT  
- `GET /api/task/all` → `checkIn`  
- `POST /api/task` body `{type:2, webapp}`  
- 加密时 `baseURL` 必须为 `"/api"`  
- 请求 `User-Agent` 必须与 WASM 内 UA 一致  
