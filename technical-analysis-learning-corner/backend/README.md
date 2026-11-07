# Analysis API

该服务直接复用项目中的：

- `scripts/pattern_core_v7.py`
- `scripts/kline_pattern_report.py`
- `fae/judgment/`

启动：

```powershell
python -m pip install -r requirements.txt
# 在 wechat-miniprogram 目录执行
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
# 或在 backend 目录执行
python -m uvicorn backend.app:app --app-dir .. --host 127.0.0.1 --port 8000
```

测试：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/analyze?symbol=sh518880"
```

小程序不能直接访问电脑的 `127.0.0.1`。联调真机前，需要将此服务部署为
HTTPS 地址，在微信公众平台添加为 `request` 合法域名，并把地址填入
`miniprogram/config.js`。

服务只返回客观识别和确定性规则解读，不调用大模型。
