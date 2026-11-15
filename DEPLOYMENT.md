# 部署说明

三种方式按场景选择：本机/内网试运行、长期运行的服务器、容器化交付。

## 0. 通用准备

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

生产环境至少设置两个变量：

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL="sqlite:////var/lib/semirel/reliability.db"   # 或 PostgreSQL
export SEMIREL_DATA_DIR="/var/lib/semirel"
```

> 未设置 `SECRET_KEY` 时使用的是仓库内的开发占位值，**不能**直接暴露到公网。

## 1. 直接运行（试运行 / 内网）

```bash
python run.py --host 0.0.0.0 --port 8000
```

- 前端与 API 同端口，无需额外配置静态服务器
- 数据库文件默认在 `data/reliability.db`
- 适合个人或小团队内网使用，不建议直接对公网开放

## 2. Systemd + Nginx（长期运行）

`/etc/systemd/system/semirel.service`：

```ini
[Unit]
Description=Semiconductor Reliability Platform
After=network.target

[Service]
Type=simple
User=semirel
WorkingDirectory=/opt/semirel
Environment=SECRET_KEY=<your-32-bytes-secret>
Environment=SEMIREL_DATA_DIR=/var/lib/semirel
ExecStart=/opt/semirel/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now semirel
```

Nginx 反代（把 `/` 全部交给 FastAPI，前端静态资源也由它提供）：

```nginx
server {
    listen 80;
    server_name reliability.example.com;

    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

HTTPS 建议用 `certbot --nginx` 签发。启用 HTTPS 后注意：匿名配额按 `request.client.host` 计算，若前面还有一层代理，需要让 uvicorn 以 `--proxy-headers --forwarded-allow-ips=127.0.0.1` 启动，否则所有匿名用户会共用同一个配额键。

```bash
uvicorn backend.app.main:app --proxy-headers --forwarded-allow-ips=127.0.0.1
```

### 多进程与 SQLite

SQLite 适合中小规模使用。`--workers > 1` 时写操作会串行排队，但不会损坏数据；若并发明显增大，建议切换 PostgreSQL：

```bash
pip install psycopg[binary]
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/semirel"
```

## 3. Docker

```bash
docker build -t semirel .
docker run -d --name semirel \
  -p 8000:8000 \
  -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -v semirel-data:/app/data \
  semirel
```

数据卷挂在 `/app/data`，对应容器内的默认 `SEMIREL_DATA_DIR`。

## 4. 数据与运维

| 事项 | 做法 |
| --- | --- |
| 备份 | 定期复制 `SEMIREL_DATA_DIR/reliability.db`（SQLite 可用 `.backup` 或停机复制） |
| 开通专业版 | `python scripts/grant_premium.py --email user@example.com` |
| 查看记录量 | `sqlite3 reliability.db "select count(*) from calculations;"` |
| 清理历史 | 界面内单条删除，或按时间批量执行 SQL（谨慎操作） |
| 日志 | 应用日志输出到 stdout，交给 systemd journald 或容器日志收集 |

## 5. 上线检查清单

- [ ] `SECRET_KEY` 已替换为随机值，且未写入仓库
- [ ] 数据库目录已做持久化与备份
- [ ] HTTPS 已启用；如经代理，`--proxy-headers` 已配置
- [ ] 免费额度（`FREE_DAILY_QUOTA` / `ANONYMOUS_DAILY_QUOTA`）符合预期
- [ ] `/docs` 是否需要对外关闭（可在 `main.py` 中设置 `docs_url=None`）
- [ ] 已运行 `python -m pytest` 全部通过
