# Technical Analysis Learning Corner

Technical Analysis Learning Corner 是一个技术分析学习小程序，提供 K 线图、形态识别、指标、均线、缠论学习和知识库入口。

## 解决的问题

初学者需要在图表、术语和规则之间来回切换。本产品把常见技术分析知识集中到一个小程序中，并提供可解释的规则结果。

## 使用方法

使用微信开发者工具导入本目录。需要在线分析时，在 `miniprogram/config.js` 填入自己的 HTTPS API 地址，并在微信平台配置合法域名。`project.config.json` 中的 AppID 由使用者自行填写。

后端依赖位于 `backend/`，安装 `backend/requirements.txt` 后按其中说明启动 FastAPI 服务。

## 核心优势

- 学习内容和交互页面集中。
- 图表、形态、指标和均线工具可以独立使用。
- 后端分析接口采用确定性规则，结果便于复查。

## 技术架构

前端使用微信小程序原生 JavaScript、WXML 和 WXSS。后端使用 Python、FastAPI、NumPy 和 Pandas，提供 HTTP API。前端通过 `miniprogram/services/analysis.js` 调用后端，未配置 API 地址时保留本地演示模式。

## 配置

请只在本机填写 AppID、CloudBase 环境 ID 和后端地址。仓库中的配置模板保持为空，不包含任何账户或环境凭证。
