# idol_show_auto_recorder

从 live48 抓取公演信息，筛选包含目标成员的场次，并写入飞书多维表。

## 配置

仓库提供 `settings.json`（无敏感信息）。你需要在同目录新建 `settings.local.json` 覆盖私有配置：
- `target.name`：目标成员名
- `feishu.*`：飞书开放平台与多维表信息

## 运行

### 直接执行一次
```bash
python main.py
```

### 托盘常驻（右下角）
```bash
python IdolShowAutoRecorder.py
```

默认每 6 小时跑一次，可在 `settings.json` 的 `runtime.interval_hours` 修改。
