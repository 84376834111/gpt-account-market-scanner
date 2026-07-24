# 安全说明

请不要在公开 Issue 中提交密钥、数据库、服务器地址或其他敏感数据。安全问题请通过 GitHub 仓库的 Private vulnerability reporting 提交。

部署时应通过环境文件设置 `LDXP_ADMIN_KEY`，并确保该文件仅对服务账户和管理员可读。数据库、代理订阅地址、扫描产物与部署机器的 Nginx 站点配置不属于源码，不应提交到仓库。
