const service = require("../../services/analysis");

var LABELS = { fast: "快线周期", slow: "慢线周期", signal: "信号周期", period: "计算周期", kSmooth: "K 平滑", dSmooth: "D 平滑", atrPeriod: "ATR 周期", multiplier: "波动倍数" };

Page({
  data: {
    symbol: "sh000001", years: 3, yearsList: [1, 2, 3, 5, 10], indicator: "macd", currentName: "MACD", loading: false, result: null, parameters: [], symbolSuggestions: [],
    indicators: [
      { key: "macd", name: "MACD", copy: "趋势动量" }, { key: "kdj", name: "KDJ", copy: "反趋势敏感区" },
      { key: "rsi", name: "RSI", copy: "强弱与冷热" }, { key: "supertrend", name: "SuperTrend", copy: "ATR 趋势线" },
      { key: "id", name: "信息离散度 · ID", copy: "涨跌集中或分散" }
    ]
  },
  handleInput: function (event) {
    var value = event.detail.value;
    this.setData({ symbol: value, symbolSuggestions: service.getSymbolSuggestions(value) });
  },
  selectSymbolSuggestion: function (event) {
    this.setData({ symbol: event.currentTarget.dataset.symbol, symbolSuggestions: [] });
  },
  selectYears: function (event) { this.setData({ years: Number(event.currentTarget.dataset.value) }); },
  selectIndicator: function (event) {
    var key = event.currentTarget.dataset.key, item = this.data.indicators.filter(function (entry) { return entry.key === key; })[0];
    this.setData({ indicator: key, currentName: item ? item.name : key, result: null, parameters: [] });
  },
  openKnowledge: function () {
    wx.setStorageSync("knowledgeFocus", this.data.indicator === "id" ? "信息离散度" : this.data.currentName);
    wx.switchTab({ url: "/pages/library/library" });
  },
  run: function () {
    var page = this; if (this.data.loading) return; this.setData({ loading: true, symbolSuggestions: [] });
    service.requestIndicator(this.data.symbol, this.data.indicator, this.data.years).then(function (result) {
      var parameters = [];
      Object.keys(result.best || {}).forEach(function (key) { if (LABELS[key]) parameters.push({ key: key, label: LABELS[key], value: result.best[key] }); });
      page.setData({ loading: false, result: result, parameters: parameters }, function () { page.drawChart(); });
    }).catch(function (error) { page.setData({ loading: false }); wx.showModal({ title: "暂时无法优化", content: error.message || "请稍后重试", showCancel: false }); });
  },

  drawChart: function () {
    var page = this;
    setTimeout(function () {
      wx.createSelectorQuery().in(page).select("#indicatorCanvas").fields({ node: true, size: true }).exec(function (items) {
        if (!items || !items[0] || !items[0].node || !page.data.result || !page.data.result.chart) return;
        var canvas = items[0].node;
        var width = items[0].width;
        var height = items[0].height;
        var info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        var ratio = Math.max(1, info.pixelRatio || 1);
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        var ctx = canvas.getContext("2d");
        if (ctx.setTransform) ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(ratio, ratio);
        page.renderChart(ctx, width, height, page.data.result.chart);
      });
    }, 60);
  },

  renderChart: function (ctx, width, height, chart) {
    var candles = chart.candles || [];
    if (!candles.length) return;
    var trendMode = chart.displayMode === "trend";
    var mainSeries = chart.mainSeries || [];
    var subSeries = chart.subSeries || [];
    var hasSub = subSeries.length > 0;
    var pad = { l: 44, r: 16, t: 22, b: 34 };
    var mainTop = pad.t;
    var mainBottom = hasSub ? height * 0.54 : height - pad.b;
    var subTop = hasSub ? height * 0.66 : mainBottom;
    var subBottom = height - pad.b;
    var chartWidth = width - pad.l - pad.r;
    var x = function (index) { return pad.l + (index + 0.5) * chartWidth / candles.length; };
    var finiteValues = function (values) { return (values || []).filter(function (value) { return value !== null && isFinite(value); }).map(Number); };
    var mainValues = [];
    candles.forEach(function (bar) { mainValues.push(Number(bar.high), Number(bar.low)); });
    mainSeries.forEach(function (series) { mainValues = mainValues.concat(finiteValues(series.values)); });
    var mainMin = Math.min.apply(null, mainValues);
    var mainMax = Math.max.apply(null, mainValues);
    var mainSpan = Math.max(mainMax - mainMin, 1e-6);
    mainMin -= mainSpan * 0.08;
    mainMax += mainSpan * 0.08;
    var yMain = function (value) { return mainTop + (mainMax - Number(value)) * (mainBottom - mainTop) / (mainMax - mainMin); };

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    function drawGrid(top, bottom, low, high, labelCount) {
      ctx.strokeStyle = "#edf0f4";
      ctx.fillStyle = "#8a909b";
      ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif';
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.setLineDash([3, 5]);
      for (var grid = 0; grid <= labelCount; grid += 1) {
        var gy = top + (bottom - top) * grid / labelCount;
        var value = high - (high - low) * grid / labelCount;
        ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(width - pad.r, gy); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillText(Number(value).toFixed(2), pad.l - 6, gy);
        ctx.setLineDash([3, 5]);
      }
      ctx.setLineDash([]);
    }
    drawGrid(mainTop, mainBottom, mainMin, mainMax, 4);
    ctx.setLineDash([]);
    var bodyWidth = Math.max(2, Math.min(7, chartWidth / candles.length * 0.58));
    if (!trendMode) {
      candles.forEach(function (bar, index) {
        var color = Number(bar.close) >= Number(bar.open) ? "#f23645" : "#089981";
        var cx = x(index);
        ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(cx, yMain(bar.high)); ctx.lineTo(cx, yMain(bar.low)); ctx.stroke();
        var top = Math.min(yMain(bar.open), yMain(bar.close));
        var bodyHeight = Math.max(1.4, Math.abs(yMain(bar.open) - yMain(bar.close)));
        ctx.fillRect(cx - bodyWidth / 2, top, bodyWidth, bodyHeight);
      });
    }
      mainSeries.forEach(function (series) {
        ctx.strokeStyle = series.color || "#2962ff"; ctx.lineWidth = trendMode && series.label === "平滑趋势" ? 2.8 : 1.7; ctx.beginPath();
        var started = false;
        (series.values || []).forEach(function (value, index) {
        if (value === null || !isFinite(value)) { started = false; return; }
        if (!started) { ctx.moveTo(x(index), yMain(value)); started = true; } else ctx.lineTo(x(index), yMain(value));
        });
        if (started) ctx.stroke();
      });
    if (hasSub) {
      var subValues = [];
      subSeries.forEach(function (series) { subValues = subValues.concat(finiteValues(series.values)); });
      var levels = chart.levels || [];
      levels.forEach(function (level) { if (level.series === undefined || level.series === 0) subValues.push(Number(level.value)); });
      var subMin = Math.min.apply(null, subValues);
      var subMax = Math.max.apply(null, subValues);
      var subSpan = Math.max(subMax - subMin, 1e-6);
      subMin -= subSpan * 0.08; subMax += subSpan * 0.08;
      var ySub = function (value) { return subTop + (subMax - Number(value)) * (subBottom - subTop) / (subMax - subMin); };
      drawGrid(subTop, subBottom, subMin, subMax, 3);
      ctx.strokeStyle = "#dfe4ec"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(pad.l, subTop - 8); ctx.lineTo(width - pad.r, subTop - 8); ctx.stroke();
      levels.forEach(function (level) {
        if (level.series !== undefined && level.series !== 0) return;
        if (level.value === null || !isFinite(level.value)) return;
        var levelY = ySub(level.value);
        ctx.strokeStyle = level.color || "#a8adb7"; ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(pad.l, levelY); ctx.lineTo(width - pad.r, levelY); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = level.color || "#8a909b"; ctx.font = '9px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textAlign = "left"; ctx.textBaseline = "bottom";
        ctx.fillText(level.label || Number(level.value).toFixed(2), pad.l + 5, levelY - 4);
      });
      subSeries.forEach(function (series) {
        ctx.strokeStyle = series.color || "#2962ff"; ctx.lineWidth = 1.6; ctx.beginPath();
        var subStarted = false;
        (series.values || []).forEach(function (value, index) {
          if (value === null || !isFinite(value)) { subStarted = false; return; }
          if (!subStarted) { ctx.moveTo(x(index), ySub(value)); subStarted = true; } else ctx.lineTo(x(index), ySub(value));
        });
        if (subStarted) ctx.stroke();
        var lastValue = (series.values || []).slice().reverse().filter(function (value) { return value !== null && isFinite(value); })[0];
        if (lastValue !== undefined) {
          ctx.fillStyle = series.color || "#2962ff"; ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textAlign = "right"; ctx.textBaseline = "middle";
          ctx.fillText(Number(lastValue).toFixed(2), width - pad.r, Math.max(subTop + 8, Math.min(subBottom - 4, ySub(lastValue))));
        }
      });
    }
    (chart.signals || []).forEach(function (signal) {
      var index = Number(signal.index);
      if (!isFinite(index) || index < 0 || index >= candles.length) return;
      var px = x(index); var py = yMain(candles[index].close);
      var color = signal.type === "referenceUp" ? "#f23645" : "#089981";
      ctx.fillStyle = color; ctx.beginPath(); ctx.arc(px, py, 3.5, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(px, mainTop); ctx.lineTo(px, mainBottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textAlign = signal.type === "referenceUp" ? "left" : "right"; ctx.textBaseline = "middle";
      ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.fillText(signal.label || "参考", Math.min(px + 5, width - 54), py + (signal.type === "referenceUp" ? 14 : -7));
    });
    ctx.fillStyle = "#8a909b"; ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textBaseline = "bottom"; ctx.textAlign = "left";
    ctx.fillText(String(chart.dates && chart.dates[0] || "").slice(0, 10), pad.l, height - 8);
    ctx.textAlign = "right";
    ctx.fillText(String(chart.dates && chart.dates[chart.dates.length - 1] || "").slice(0, 10), width - pad.r, height - 8);
  }
});
