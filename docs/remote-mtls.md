# 远程部署：域名 + mTLS（方案 A）

> 状态：**运维规范 / 目标态**。业务代码暂不改。  
> 目标：家用电脑跑 Local Agent（只出站）；VPS 跑 Server Center；用自有域名访问；**未持有你签发的客户端证书则无法访问域名，也无法与 Server 通信**。

相关：根 [README](../README.md)、[模块通信约定](../Local_agent/docs/module-communication.md)。

---

## 1. 目标拓扑

```text
浏览器（导入 client.p12）
        │  HTTPS + 客户端证书 (mTLS)
        ▼
  https://agent.example.com
        │  Caddy / Nginx（公网 443）
        │  ssl_verify_client on
        ▼
  Server Center 仅听 127.0.0.1:8765
        ▲
        │  出站 HTTPS/WSS + 同一套（或专用）client cert
Local Agent（家用电脑，LA_HOST=127.0.0.1）
```

| 角色 | 放哪 | 公网暴露 |
|------|------|----------|
| Server Center | 租用 VPS | **否**（只本机回环） |
| 反代 + mTLS | 同 VPS | **仅 443** |
| Local Agent | 你的电脑 | **否**（只出站） |
| 本地 LLM（Ollama 等） | 你的电脑 | **否** |

**不要**：把 `:8765` / `:8770` 映射到公网；不要把 CA 私钥放在 VPS 上。

---

## 2. 当前代码阻塞（先读）

今日联调已支持：`LA_SERVER_CENTER_URL=https://…` 时 Local 会自动用 `wss://`（见 `ws_listener` / `terminal/bridge`）。

**尚未支持**：出站 HTTP/WS **附带客户端证书**。因此：

| 阶段 | 能否开全站 `ssl_verify_client on` |
|------|-----------------------------------|
| 只做反代 HTTPS、Server 绑回环、关终端 | ✅ 可立刻做（无 mTLS） |
| 浏览器 + Agent 全站 mTLS | ❌ 需先完成文末「代码待改」后再切 |

建议节奏：

1. **现在**：按 §4～§5 把 Server 收到回环 + HTTPS 反代（可先 `verify_client` 关闭），域名可访问但**仍不安全到可上公网给人用的程度**。
2. **代码就绪后**：签发客户端证书 → 反代打开强制 mTLS → Local 配置 cert 路径。
3. **切流检查表**：§8。

下文按**目标态（mTLS 全开）**写操作步骤；涉及「代码未就绪」处会标注。

---

## 3. 证书体系

### 3.1 角色

| 证书 | 用途 | 存放 |
|------|------|------|
| **域名服务端证书** | HTTPS（浏览器锁） | VPS 反代；Let's Encrypt 自动续期即可 |
| **你的私有 CA** | 签发客户端证书 | **离线机 / U 盘**；私钥永不上传 VPS |
| **client-browser** | 浏览器访问 UI | 你的电脑（`.p12`） |
| **client-localagent** | Local → Server 出站 | 家用电脑（`cert.pem` + `key.pem`） |

单用户够用：1 张浏览器证 + 1 张 Agent 证。换设备再签一张，丢了就吊销。

### 3.2 在离线机签发（OpenSSL 示例）

以下在**不联网或可信本机**执行；目录示例 `~/homeagent-ca/`。

```bash
mkdir -p ~/homeagent-ca/{certs,private,csr,crl}
cd ~/homeagent-ca
chmod 700 private

# 1) 私有 CA（妥善备份 private/ca.key）
openssl genrsa -aes256 -out private/ca.key 4096
openssl req -new -x509 -days 3650 -key private/ca.key -out certs/ca.crt \
  -subj "/CN=HomeAgent Personal CA"

# 2) 浏览器客户端证书
openssl genrsa -out private/browser.key 2048
openssl req -new -key private/browser.key -out csr/browser.csr \
  -subj "/CN=homeagent-browser"
openssl x509 -req -in csr/browser.csr -CA certs/ca.crt -CAkey private/ca.key \
  -CAcreateserial -out certs/browser.crt -days 365 \
  -extfile <(printf "extendedKeyUsage=clientAuth")

# 导出给 Windows / macOS 导入（设置导出密码）
openssl pkcs12 -export -out certs/browser.p12 \
  -inkey private/browser.key -in certs/browser.crt -certfile certs/ca.crt

# 3) Local Agent 客户端证书
openssl genrsa -out private/localagent.key 2048
openssl req -new -key private/localagent.key -out csr/localagent.csr \
  -subj "/CN=homeagent-localagent"
openssl x509 -req -in csr/localagent.csr -CA certs/ca.crt -CAkey private/ca.key \
  -CAcreateserial -out certs/localagent.crt -days 365 \
  -extfile <(printf "extendedKeyUsage=clientAuth")

# 拷到家用电脑（勿提交 git）
# certs/ca.crt
# certs/localagent.crt + private/localagent.key
# certs/browser.p12 → 只进浏览器
```

Windows 若无 `<(printf …)`，可把扩展项写成 `client_ext.cnf` 再 `-extfile client_ext.cnf`。

### 3.3 吊销列表（可选但建议）

```bash
# 首次
touch index.txt
echo 1000 > serial
# 按你的 openssl.cnf 配置 [CA_default] 后：
openssl ca -revoke certs/browser.crt -keyfile private/ca.key -cert certs/ca.crt
openssl ca -gencrl -keyfile private/ca.key -cert certs/ca.crt -out crl/ca.crl
```

把 `ca.crt`（以及若启用则 `ca.crl`）拷到 **VPS 反代可读路径**，例如 `/etc/homeagent/tls/ca.crt`。  
**不要**拷贝 `private/ca.key`。

---

## 4. VPS：Server Center

### 4.1 进程绑定

环境变量 / `.env`：

```bash
SC_HOST=127.0.0.1
SC_PORT=8765
# 公网阶段建议先关终端；需要时再开，且必须已在 mTLS 之后
SC_TERMINAL_ENABLED=false
```

确认未在云厂商安全组放行 `8765`。仅放行 `443`（及可选 `80` 给 ACME）。

### 4.2 构建前端并启动

按 [Server_center/README.md](../Server_center/README.md)：`npm run build` 后由 FastAPI 托管 static；systemd 或手动 `uvicorn`，保证只监听 `127.0.0.1:8765`。

```bash
ss -lntp | grep 8765
# 应看到 127.0.0.1:8765，而不是 0.0.0.0:8765
```

---

## 5. VPS：反代 + mTLS

下方以 **Caddy** 为主（配置短）；Nginx 等价见附录。

### 5.1 过渡：仅 HTTPS（无客户端校验）

代码未支持 Agent 客户端证书前，可先：

```caddyfile
agent.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

此时有传输加密，**仍无身份门禁**，勿当成最终方案。

### 5.2 目标：强制 mTLS

将 `ca.crt` 放到例如 `/etc/homeagent/tls/ca.crt`。

```caddyfile
agent.example.com {
    tls {
        client_auth {
            mode require
            trust_pool file /etc/homeagent/tls/ca.crt
        }
    }
    reverse_proxy 127.0.0.1:8765
}
```

效果：无有效客户端证书时，TLS 握手失败，应用层不可达（含 `/ws/*`、`/api/*`、静态 UI）。

可选：用 `mode request` 做灰度（先要证但不拒），确认浏览器与 Agent 都正常后再改 `require`。

### 5.3 DNS

域名 A/AAAA 指向 VPS 公网 IP。Local Agent 的 `LA_SERVER_CENTER_URL` **写域名**，不要写漂移的 IP（除非你做了固定 IP 且能接受改配置）。

---

## 6. 浏览器侧

1. 双击或系统导入 `browser.p12`（Windows「用户证书」/ macOS 钥匙串）。
2. 信任提示按系统走；访问 `https://agent.example.com`。
3. 首次应弹出选择客户端证书 → 选 `homeagent-browser`。
4. 无证书的另一台设备访问 → 应握手失败或浏览器报证书错误。

Chrome 若一直不弹窗：检查证书是否进了「个人」存储、是否过期、CN/EKU 是否含 `clientAuth`。

---

## 7. Local Agent 侧（家用电脑）

### 7.1 现即可配（不依赖 mTLS 代码）

```bash
LA_HOST=127.0.0.1
LA_PORT=8770
LA_SERVER_CENTER_URL=https://agent.example.com
LA_TERMINAL_ENABLED=false
```

- `:8770` 勿对局域网/公网开放。  
- 仅 HTTPS、反代未开 `require` 时，上述即可联通。

### 7.2 目标态配置（代码支持后）

证书建议路径（示例，自行调整，**加入 .gitignore**）：

```text
Local_agent/keys/mtls/
  ca.crt              # 可选：校检服务端时若不用系统根，一般 LE 不需要
  localagent.crt
  localagent.key
```

预期环境变量（名称以实现为准，此处为约定草案）：

```bash
LA_SERVER_CENTER_URL=https://agent.example.com
LA_MTLS_CLIENT_CERT=keys/mtls/localagent.crt
LA_MTLS_CLIENT_KEY=keys/mtls/localagent.key
# LA_MTLS_CA_CERT=   # 通常留空，用系统信任 LE
```

---

## 8. 切换检查表

### 上线前

- [ ] `SC_HOST=127.0.0.1`，安全组无 8765
- [ ] `LA_HOST=127.0.0.1`
- [ ] 终端开关默认 false（或接受「mTLS 后的神权 shell」风险）
- [ ] CA 私钥离线备份；VPS 仅有 `ca.crt`
- [ ] 浏览器 p12 已导入并能打开 UI
- [ ] **代码已支持** Agent 出站 client cert（见 §10）
- [ ] 反代 `require` 前用 `request` 观察日志是否见到 Agent 证书 CN

### 验证

| 检查 | 期望 |
|------|------|
| 无客户端证书访问域名 | 失败 |
| 有 browser 证书打开 UI | 成功 |
| Local 带 agent 证书收发消息 | 主对话通 |
| 家用电脑关掉 Local | UI 仍开，但模块无响应 |
| 直接访问 `http://VPS:8765` | 不通 |

### 回滚

1. 反代改回不校验客户端 / 或临时 `mode request`
2. 保留 HTTPS 与回环绑定
3. 排查证书路径与进程日志后再开 `require`

---

## 9. 日常运维

### 9.1 Let's Encrypt 服务端证书

Caddy / certbot 自动续期即可；与私有 CA **无关**。

### 9.2 客户端证书续期（建议 365 天）

到期前在离线 CA 重签同 CN 或新 CN → 替换：

- 浏览器：导入新 p12，删除旧证
- Agent：替换 `localagent.crt/key`，重启 Local Agent
- 旧证：吊销并更新 VPS 上 `ca.crl`（若启用 CRL）

### 9.3 证书丢失 / 电脑送修

1. 离线 CA **吊销**对应证书，更新 CRL（或直接换新 CA 并轮换 VPS 信任锚——单用户可接受）
2. 重签并分发新证
3. 若怀疑私钥泄露：视同丢失，必须吊销

### 9.4 换域名 / 换 VPS

1. DNS 指向新机器
2. 新 VPS：只装 `ca.crt` + 反代配置；Server 仍绑 `127.0.0.1`
3. Local 的 `LA_SERVER_CENTER_URL` 改新域名
4. 浏览器书签更新；客户端证书**不用**因换 IP 而重签（CN 未绑 IP）

### 9.5 备份

| 物品 | 备份 |
|------|------|
| `private/ca.key` + `certs/ca.crt` | 加密离线，两份异地 |
| `messages.db` 等 Server data | VPS 常规备份（内容仍为明文，靠磁盘与访问控制） |
| Local `data/`、`keys/` | 家用电脑备份；mtls key 权限收紧 |

### 9.6 日志与审计

- 反代：记录 TLS 客户端证书 CN（Caddy/Nginx 可配）→ 区分 browser vs localagent
- Server `messages.db`：业务审计；不能替代入口鉴权
- 发现陌生 CN：立刻吊销并查 VPS 是否被改配置

---

## 10. 代码待改（本文不实施，仅清单）

实现前**不要**在反代上对 Agent 使用的路径强制 `require`，否则 Local 会连不上。

| 优先级 | 位置 | 改动要点 |
|--------|------|----------|
| P0 | `shared/server_center/client.py` | `httpx.AsyncClient` 传入 `cert=(cert, key)`；配置项读路径 |
| P0 | `shared/server_center/ws_listener.py` | `websockets.connect(..., ssl=ssl_context)`，context 加载 client cert |
| P0 | `modules/terminal/bridge.py` | 同上，否则一开终端就会在 mTLS 下失败 |
| P0 | `app/config.py` + `.env.example` | `LA_MTLS_CLIENT_CERT` / `KEY`（及文档说明） |
| P1 | 启动自检 | 若 URL 为 https 且反代已 require，缺证则打明确错误日志 |
| P2 | Server 应用层 | 可选：校验反代传入的证书 DN 头（需反代 `header_up`）；**有 mTLS 时非必须** |
| P2 | 注册 `clients` | 可选：client_id 与证书指纹绑定，防注册劫持 |
| — | 前端 | **通常不用改**（浏览器选系统客户端证书） |
| — | 现有 RSA body 加密 | **可保留**作纵深；mTLS 已提供传输层机密性与身份 |

**明确不做（除非产品要多租户）**：为「证书」重写整套消息协议；把 Local HTTP API 挂到域名。

---

## 11. 安全预期（方案 A 之后仍残留）

mTLS 解决的是：**谁能连上控制面**。

仍须自行约束：

- 终端 = 本机 shell，有证即有神权 → 公网阶段默认关
- Executor 规则仍是启发式，不是 OS 沙箱
- `messages.db` / `llm.db` 落盘明文 → 靠 VPS 磁盘加密与权限
- 提示注入仍可能驱动 FC → 红灯人工批、慎用 auto-approve

---

## 附录 A：Nginx 等价片段

```nginx
server {
    listen 443 ssl;
    server_name agent.example.com;

    ssl_certificate     /etc/letsencrypt/live/agent.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agent.example.com/privkey.pem;

    ssl_client_certificate /etc/homeagent/tls/ca.crt;
    ssl_verify_client on;
    # ssl_crl /etc/homeagent/tls/ca.crl;  # 若启用吊销

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

WebSocket 超时与 `Upgrade` 头必配，否则 UI/Agent 频道会断。

---

## 附录 B：推荐目录（VPS）

```text
/etc/homeagent/tls/
  ca.crt          # 私有 CA 公钥（信任锚）
  ca.crl          # 可选
/var/lib/homeagent/Server_center/   # 应用与 data/（按你实际部署路径）
```

systemd 中 Server 的 `Environment=SC_HOST=127.0.0.1` 与文档 §4 一致即可。
