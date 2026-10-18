---
title: alembic.ini 的注释为什么全是英文
date: 2026-10-18
tags:
  - Alembic
  - 编码
  - Windows
draft: false
---

打开 backend/alembic.ini，会发现注释全是英文，跟项目里满屏中文注释的 `.py` 文件格格不入。这是被中文 Windows 逼的。

Python 的 configparser 读 ini 文件时，用的编码是 `encoding="locale"`，也就是跟随系统。这台机器上就是 GBK。如果 ini 存成 UTF-8，里面又写了中文注释，读的那一步会直接抛 UnicodeDecodeError，迁移根本跑不起来。所以这个文件里只放 ASCII，连一句中文注释都不敢留。

好消息是这个限制只落在 ini 上。Python 源码文件默认按 UTF-8 读，所以 `.py` 里的中文注释照常；Astro 那边同理，`.astro`、`.tsx` 里的中文也没问题。不是「整个项目不能用中文」，只是这一个配置文件要守规矩。

顺带一提，这个 ini 里的 `sqlalchemy.url` 是留空的：

```ini
# Left empty on purpose; env.py sets it dynamically
sqlalchemy.url =
```

连接串由 backend/alembic/env.py 运行时从 `settings.DATABASE_URL` 注入。这样 SQLite 和 MySQL 共用一份迁移配置，切库只改 `.env`，不用动这里。
