# 半导体可靠性计算平台

面向半导体器件与模组的可靠性计算工具。FastAPI 后端 + Bootstrap 5 前端，内置 **MTBF 与失效率**、**Duane 可靠性增长**、**试验样本量** 三个计算器，支持用户注册登录、每日配额、历史记录存档，以及 CSV / Excel / JSON 导出。

> 目标不是"给一个数字"，而是把模型、公式、假设和置信区间一起交代清楚，便于写进试验报告或评审材料。

---

## 功能一览

| 模块 | 能力 |
| --- | --- |
| MTBF 与失效率 | 由失效数 + 总器件小时反推 MTBF、λ、FIT；卡方**精确**置信区间（定时/定数截尾）；任务时间可靠度；B1/B10/B50 寿命；可靠度曲线 |
| Duane 可靠性增长 | 失效时刻序列 → 双对数回归得到 α、β；累计/瞬时 MTBF；R²、β 标准误、t 检验、β 置信区间；目标时刻预测区间；目标 MTBF 反算所需试验时间；增长曲线图 |
| 试验样本量 | 成功运行（零失效）、二项允许失效、指数定时截尾、指数定数截尾；样本量与试验时间；c=0~5 方案对比表；按单台时长换算台数 |
| 账户体系 | 邮箱注册 / 登录（PBKDF2 口令哈希 + JWT）；免费额度按账号计，匿名按 IP 哈希计；专业版无限次 |
| 历史与导出 | 登录用户的每次计算自动入库，可回看、载入参数、删除；单条结果导出 CSV/XLSX/JSON；历史批量导出 |

## 技术栈

- 后端：Python 3.11+、FastAPI、SQLAlchemy 2、SQLite、SciPy（χ²、t、二项分布）
- 前端：Bootstrap 5.3 + Bootstrap Icons + Chart.js 4（原生 JS，无构建步骤）
- 导出：csv 标准库 + openpyxl（Excel 带样式、每个表格独立页签）
- 测试：pytest + FastAPI TestClient

## 目录结构

```
.
├── backend/
│   ├── __init__.py
│   └── app/
│       ├── main.py            # FastAPI 应用入口、路由挂载、前端静态目录
│       ├── config.py          # 环境变量配置
│       ├── database.py        # SQLAlchemy 引擎与会话
│       ├── models.py          # User / Calculation / DailyUsage
│       ├── schemas.py         # 请求与响应模型
│       ├── security.py        # PBKDF2 口令哈希、JWT 签发与校验
│       ├── deps.py            # 认证依赖、每日配额
│       ├── exporting.py       # CSV / XLSX / JSON 报告构建
│       ├── calculators/       # 计算内核（纯函数式，可独立测试）
│       │   ├── base.py        # 统一输入校验与结果结构
│       │   ├── mtbf.py
│       │   ├── duane.py
│       │   └── sample_size.py
│       └── routers/           # auth / calculators / history / export
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── scripts/grant_premium.py   # 运维脚本：按邮箱开通专业版
├── tests/                     # 计算正确性 + 接口测试
├── requirements.txt
├── run.py                     # 本地启动脚本
├── Dockerfile
└── DEPLOYMENT.md
```

## 快速开始

```bash
# 1. 虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. 依赖
pip install -r requirements.txt

# 3. 启动
python run.py            # http://127.0.0.1:8000
python run.py --reload   # 开发模式，代码改动自动重载
```

打开 <http://127.0.0.1:8000> 即为完整界面，<http://127.0.0.1:8000/docs> 是自动生成的 OpenAPI 文档。

首次启动会在 `data/` 下创建 SQLite 数据库 `reliability.db`，无需手动建表。

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SECRET_KEY` | 开发占位值 | **生产环境必须更换**，建议 32 字节以上随机串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | 登录令牌有效期（分钟） |
| `FREE_DAILY_QUOTA` | `20` | 登录用户每日免费计算次数 |
| `ANONYMOUS_DAILY_QUOTA` | `5` | 未登录用户每日计算次数（按 IP 哈希计） |
| `SEMIREL_DATA_DIR` | `<仓库>/data` | 数据库与运行数据目录 |
| `DATABASE_URL` | `sqlite:///.../reliability.db` | 可切换到 PostgreSQL 等 |

复制 `.env.example` 后按需修改，再通过 shell 或容器注入（项目不自动读取 `.env`，避免生产环境误用）。

## API 一览

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/health` | 否 | 健康检查 |
| GET | `/api/calculators` | 否 | 计算器目录（含表单定义） |
| GET | `/api/calculators/{id}` | 否 | 单个计算器元信息 |
| GET | `/api/calculators/{id}/example` | 否 | 示例输入 |
| POST | `/api/calculators/{id}/calculate` | 可选 | 执行计算；未登录返回结果不入库 |
| POST | `/api/auth/register` | 否 | 注册并返回令牌 |
| POST | `/api/auth/login` | 否 | 登录返回令牌 |
| GET | `/api/auth/me` | 可选 | 当前用户与剩余配额 |
| POST | `/api/auth/logout` | 否 | 客户端丢弃令牌即可 |
| GET | `/api/history` | 是 | 历史记录列表 |
| GET | `/api/history/{id}` | 是 | 单条记录 |
| DELETE | `/api/history/{id}` | 是 | 删除记录 |
| GET | `/api/history/export?format=csv\|xlsx\|json` | 是 | 批量导出 |
| POST | `/api/export/calculation` | 否 | 导出当前结果（CSV/XLSX/JSON） |

计算请求体统一为 `{"inputs": {...}}`，字段定义从 `/api/calculators` 获取，前端据此动态生成表单。

## 计算模型

### 1. MTBF 与失效率

指数分布（恒定失效率）假设下：

```
λ = r / T                       r：失效数，T：总器件小时 Σ(样本数 × 时长)
MTBF = 1 / λ = T / r
FIT  = λ × 10^9                 失效数 / 十亿器件小时
R(t) = exp(-t / MTBF)
Bx   = MTBF × ln(1/(1-x%))      Bx 寿命
```

置信区间用卡方精确法：

```
定时截尾：MTBF 下限 = 2T / χ²(1-α/2, 2r+2)
          MTBF 上限 = 2T / χ²(α/2, 2r)
定数截尾：上下限自由度均为 2r
单侧下限 = 2T / χ²(1-α, 2r+2)   （定时截尾；定数截尾用 2r）
```

零失效时点估计为 ∞，工程上应引用单侧置信下限。直接输入失效率的模式不提供区间估计——区间需要样本信息，这一点在界面与结果说明中都会明确提示，而不是用"假定失效数"糊弄过去。

### 2. Duane 可靠性增长

```
M_c(T) = α · T^β                 累计 MTBF
M_i(T) = M_c(T) / (1-β)          瞬时 MTBF
增长率 = 1 - β
```

- 对每个失效时刻 `T_i`，取累计 MTBF `M_c(i) = T_i / i`，再对 `ln M_c ~ ln T` 做最小二乘回归
- β 的标准误、t 值、p 值、R² 一并给出，用于判断增长趋势是否显著
- 目标时刻预测区间在 log 空间按 t 分布预测区间计算后取指数还原
- 瞬时 MTBF 是工程当前水平，累计 MTBF 含历史平均，两者不要混用
- 目标 MTBF 反算：`T = (M(1-β)/α)^(1/β)`（瞬时口径）

### 3. 试验样本量

```
成功运行（零失效）：n = ceil( ln(1-C) / ln(R) )
二项允许失效：最小 n 使 P(X ≤ c | q = 1-R) ≤ 1-C（二项精确 CDF 二分求解）
指数定时截尾：T = θ0 · χ²(1-C, 2c+2) / 2
指数定数截尾：T = θ0 · χ²(1-C, 2c) / 2
所需台数：n = ceil(T / 单台时长)
```

## 测试

```bash
python -m pytest
```

31 项用例，覆盖：

- MTBF 点估计、FIT 换算、χ² 临界值对照（如 r=2、T=200000、90% 置信 → 下限 31767 h）、零失效单侧下限、Bx 寿命
- Duane 用已知 α、β 合成失效时刻，验证回归能否还原参数、瞬时 MTBF 是否等于 `M_c/(1-β)`、目标时间规划公式、非法输入拒绝
- 样本量闭式解（R=0.9、C=90 → 22 台）、二项方案的最小性验证（少一台即不满足）、χ² 方案总数、台数换算
- 接口链路：健康检查、计算器目录、匿名计算与配额、参数校验、注册/登录/重复注册、鉴权后入库、历史查询、三种格式导出、删除记录、未登录 401

## 部署

见 [DEPLOYMENT.md](DEPLOYMENT.md)：直接以 uvicorn 运行、Systemd + Nginx、Docker 三种方式，以及密钥、备份与 HTTPS 注意事项。

## 安全与边界

- 口令用 PBKDF2-HMAC-SHA256（26 万轮）加盐存储；令牌为 HS256 JWT，仅通过 `Authorization: Bearer` 传递（不使用 Cookie，避免 CSRF 面）
- 所有计算输入在后端做类型与范围校验，输出统一序列化，避免 `Infinity` / `NaN` 破坏 JSON
- Excel 导出对以 `= + - @` 开头的文本按纯文本写入，防止公式注入
- 本工具用于工程估算与方案比较，不替代认证试验或正式可靠性报告；标准编号仅表示方法出处，不代表合规认证

## 许可证

MIT
