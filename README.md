# LDXP 扫货台

一个面向 `pay.ldxp.cn` 和 `catfk.com` 公开店铺的轻量比价看板。服务端定时采集商品名称、价格和库存，按关键词分类，并通过 SSE 将结果逐条推送到网页，扫描期间不会阻塞页面。

## 界面预览

![LDXP 扫货台界面预览](docs/images/dashboard.png)

## 功能

- 内置 Plus、GPT Free/非 Plus、Team、Pro、K12、Cursor、Codex、Claude、Kiro、Gemini、邮箱、接码等关键词；Plus 与非 Plus 账号会进一步按已接码、未接码拆分。
- 支持在网页中添加、启停和删除公开店铺链接；`catfk.com` 商品链接也可直接粘贴，程序会反查所属店铺。
- 内置 17 个已验证公开店铺，并定期从爱比价公开社区自动发现新链接。
- SQLite 持久化商品、价格和库存变化。
- 浏览器可用当前设备网络执行全量扫描、仅刷新当前筛选结果或刷新单件商品，并把结果回传服务器。
- 服务器手动扫描和自动调度只允许在服务器后台控制，网页不暴露主动扫描、暂停或开启自动扫描入口。
- 手机和桌面端自适应，无前端或 Python 第三方依赖。

## 本地运行

```powershell
$env:LDXP_SCAN_INTERVAL = "900"
python .\app.py
```

打开 `http://127.0.0.1:8765/`。服务端主动扫描与调度接口必须携带后台密钥；未配置密钥时这些接口一律拒绝访问。

如需自定义配置，可复制 `.env.example` 中的变量到进程管理器或私有环境文件。程序不会自动读取 `.env`；该文件仅作为配置清单示例。

可用环境变量：

- `LDXP_HOST`：监听地址，默认 `127.0.0.1`
- `LDXP_PORT`：监听端口，默认 `8765`
- `LDXP_DB_PATH`：SQLite 路径，默认 `data/ldxp.db`
- `LDXP_AUTO_SCAN_ENABLED`：是否在启动后定时自动扫描，默认 `true`
- `LDXP_SCAN_INTERVAL`：自动扫描间隔秒数，默认 `900`（15 分钟）
- `LDXP_SOURCE_INTERVAL`：流式扫描中两个店铺的最小启动间隔，默认 `15` 秒
- `LDXP_DISCOVERY_INTERVAL`：自动发现公开店铺链接的间隔秒数，默认 `21600`（6 小时）
- `LDXP_DISCOVERY_URL`：公开源发现接口，默认使用爱比价社区帖子接口
- `LDXP_PAGE_SIZE`：每次分页请求的商品数，默认 `300`
- `LDXP_MAX_PAGES`：每个店铺商品类型的最大页数，默认 `20`
- `LDXP_PAGE_DELAY`：同一商品类型两页之间的等待秒数，默认 `0.05`
- `LDXP_REQUEST_TIMEOUT`：单次 LDXP 请求超时秒数，默认 `20`
- `CATFK_BASE_URL`：云猫寄售公开站点地址，默认 `https://catfk.com`
- `LDXP_FAILOVER_PROXY_URL`：可选 HTTP 备用代理；直连失败后才使用
- `LDXP_DIRECT_ATTEMPTS`：直连尝试次数，默认 `1`
- `LDXP_PROXY_ATTEMPTS`：备用代理尝试次数，默认 `3`
- `LDXP_RETRY_DELAY`：重试间隔秒数，默认 `0.4`
- `LDXP_ADMIN_KEY`：服务器后台扫描控制密钥，部署脚本会自动生成且不会输出密钥

## 服务器后台扫描命令

部署后通过 SSH 使用以下命令，网页端没有这些控制入口：

```bash
sudo ldxp-scanctl status
sudo ldxp-scanctl enable 15
sudo ldxp-scanctl disable
sudo ldxp-scanctl interval 30
sudo ldxp-scanctl scan
sudo ldxp-scanctl discover
```

## 数据源说明

LDXP 的公开首页没有全站商品目录。每个公开店铺由 `/shop/{token}` 链接承载，因此无法通过 LDXP 接口证明已枚举所有私下店铺。程序首次运行会加入已验证的公开店铺，并从爱比价公开社区的帖子、回复和商品链接持续发现新源；未在公开网页出现的店铺仍需手动添加。

## 测试

```powershell
python -m unittest discover -s tests -v
```

## Ubuntu 一键部署

适用于全新的 Ubuntu/Debian 主机。脚本会安装 `git`、`python3` 和证书包，将源码检出到 `/opt/ldxp-scanner-source`，再创建并启动 `ldxp-scanner` 专用服务账户。默认只监听 `127.0.0.1:8765`，不会自动公开端口。

```bash
curl -fsSL https://raw.githubusercontent.com/84376834111/gpt-/main/deploy/bootstrap.sh | sudo bash
```

如需接入已有 Nginx 站点，明确传入该机器的站点配置路径和公开地址：

```bash
curl -fsSL https://raw.githubusercontent.com/84376834111/gpt-/main/deploy/bootstrap.sh | \
  sudo env \
    LDXP_NGINX_SITE=/etc/nginx/sites-available/example.com \
    LDXP_PUBLIC_URL=https://example.com/ldxp/ \
    bash
```

可通过 `LDXP_REPOSITORY`、`LDXP_REF` 和 `LDXP_SOURCE_DIR` 覆盖源码仓库、分支和检出目录。更新时脚本只会更新来源一致且没有本地改动的检出目录。

## 手动 Ubuntu 部署

systemd 与 Nginx 部署文件位于 `deploy/`。安装脚本默认只启动本机 `127.0.0.1:8765` 服务；如需把 `/ldxp/` 注入已有 Nginx 站点，显式传入该机器上的私有配置路径：

```bash
sudo env \
  LDXP_NGINX_SITE=/etc/nginx/sites-available/example.com \
  LDXP_PUBLIC_URL=https://example.com/ldxp/ \
  bash deploy/install.sh
```

`LDXP_NGINX_SITE` 和 `LDXP_PUBLIC_URL` 不设置时，安装脚本不会读取或修改 Nginx。生产环境的域名、IP、数据库、`/etc/ldxp-scanner.env`、代理订阅地址和采集结果都属于机器私有数据，不应提交到源码仓库。

## 使用边界

本项目只处理公开页面和公开接口中的商品信息。部署者需要自行确认数据源条款、访问频率和当地法律要求，并为自己的使用方式负责。

## 许可证

本项目使用 [MIT License](LICENSE)。
