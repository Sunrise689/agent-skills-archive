const service = require("../../services/analysis");

Page({
  data: {
    symbol: "sh000001",
    years: 5,
    yearsList: [1, 2, 3, 5, 10],
    method: "single",
    mode: "basic",
    methodLabel: "单均线",
    modeLabel: "基础模式",
    methods: [
      { key: "single", label: "单均线" },
      { key: "cross", label: "双均线" },
      { key: "triple", label: "三均线" },
      { key: "midline", label: "中间线" }
    ],
    modes: [
      { key: "basic", label: "基础模式" },
      { key: "adaptive", label: "自适应模式" }
    ],
    loading: false,
    result: null,
    selectedPeriodsLabel: "",
    symbolSuggestions: []
  },
  handleInput: function (event) {
    var value = event.detail.value;
    this.setData({ symbol: value, symbolSuggestions: service.getSymbolSuggestions(value) });
  },
  selectSymbolSuggestion: function (event) {
    this.setData({ symbol: event.currentTarget.dataset.symbol, symbolSuggestions: [] });
  },
  selectYears: function (event) { this.setData({ years: Number(event.currentTarget.dataset.value) }); },
  selectMethod: function (event) {
    var key = event.currentTarget.dataset.value;
    var item = this.data.methods.filter(function (entry) { return entry.key === key; })[0];
    this.setData({ method: key, methodLabel: item ? item.label : key, result: null, symbolSuggestions: [] });
  },
  selectMode: function (event) {
    var key = event.currentTarget.dataset.value;
    var item = this.data.modes.filter(function (entry) { return entry.key === key; })[0];
    this.setData({ mode: key, modeLabel: item ? item.label : key, result: null });
  },
  run: function () {
    var page = this;
    if (this.data.loading) return;
    this.setData({ loading: true });
    service.requestMovingAverage(this.data.symbol, this.data.years, 5, this.data.method, this.data.mode).then(function (result) {
      var colors = ["#2962ff", "#f59e0b", "#8b5cf6"];
      result.chartLines = (result.chartLines || []).map(function (line, index) {
        return Object.assign({}, line, { color: line.color || colors[index] || "#59645e" });
      });
      result.valleyLines = (result.valleyLines || []).map(function (line, index) {
        return Object.assign({}, line, { color: line.color || ["#ef5350", "#f0a044", "#2962ff"][index] });
      });
      page.setData({
        loading: false,
        result: result,
        selectedPeriodsLabel: (result.selectedPeriods || []).length ? (result.selectedPeriods || []).join(" / ") : "—"
      }, function () { page.drawChart(); });
    }).catch(function (error) {
      page.setData({ loading: false });
      wx.showModal({ title: "暂时无法计算", content: error.message || "请稍后重试", showCancel: false });
    });
  },
  drawChart: function () {
    var page = this;
    setTimeout(function () {
      wx.createSelectorQuery().in(page).select("#maCanvas").fields({ node: true, size: true }).exec(function (items) {
        if (!items || !items[0] || !items[0].node) return;
        var canvas = items[0].node, width = items[0].width, height = items[0].height;
        var info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        var ratio = Math.max(1, info.pixelRatio || 1); canvas.width = width * ratio; canvas.height = height * ratio;
        var ctx = canvas.getContext("2d");
        if (ctx.setTransform) ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(ratio, ratio); page.renderChart(ctx, width, height, page.data.result.chart || [], page.data.result.chartLines || [], page.data.result.bias || {}, page.data.result.valleySignals || [], page.data.result.valleyLines || []);
      });
    }, 60);
  },
  renderChart: function (ctx, width, height, rows, chartLines, bias, valleySignals, valleyLines) {
    if (!rows.length) return;
    var pad = { l: 46, r: 14, t: 20, b: 34 };
    var values = [];
    rows.forEach(function (row) { [row.close, row.center, row.cheap, row.worryFree].forEach(function (v) { if (v !== null && isFinite(v)) values.push(Number(v)); }); });
    (chartLines || []).forEach(function (line) { (line.values || []).forEach(function (v) { if (v !== null && isFinite(v)) values.push(Number(v)); }); });
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values), span = Math.max(max - min, 1e-6); min -= span * .08; max += span * .08;
    var x = function (i) { return pad.l + i * (width - pad.l - pad.r) / Math.max(rows.length - 1, 1); };
    var y = function (v) { return pad.t + (max - v) * (height - pad.t - pad.b) / (max - min); };
    ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "#edf0f4"; ctx.lineWidth = 1; ctx.setLineDash([3, 5]);
    ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.fillStyle = "#8a909b"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
    for (var g = 0; g <= 4; g += 1) {
      var gy = pad.t + g * (height - pad.t - pad.b) / 4;
      var price = max - g * (max - min) / 4;
      ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(width - pad.r, gy); ctx.stroke();
      ctx.fillText(price.toFixed(2), pad.l - 6, gy);
    }
    ctx.setLineDash([]);
    function line(key, color, lineWidth) {
      ctx.strokeStyle = color; ctx.lineWidth = lineWidth; ctx.beginPath(); var started = false;
      rows.forEach(function (row, i) {
        var v = row[key];
        if (v === null || !isFinite(v)) { started = false; return; }
        if (!started) { ctx.moveTo(x(i), y(v)); started = true; } else ctx.lineTo(x(i), y(v));
      });
      if (started) ctx.stroke();
    }
    if (rows.some(function (row) { return row.cheap !== null && row.worryFree !== null; })) {
      ctx.fillStyle = "rgba(8,153,129,.10)"; ctx.beginPath(); var valid = rows.map(function (row, i) { return { row: row, i: i }; }).filter(function (item) { return item.row.cheap !== null && item.row.worryFree !== null; });
      valid.forEach(function (item, index) { var px = x(item.i), py = y(item.row.cheap); if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py); });
      valid.slice().reverse().forEach(function (item) { ctx.lineTo(x(item.i), y(item.row.worryFree)); }); ctx.closePath(); ctx.fill();
    }
    line("close", "#4f5665", 1.3); line("center", "#2962ff", 1.8); line("cheap", "#f59e0b", 1.4); line("worryFree", "#089981", 1.4);
    (chartLines || []).forEach(function (chartLine, lineIndex) {
      ctx.strokeStyle = chartLine.color || ["#2962ff", "#f59e0b", "#8b5cf6"][lineIndex] || "#59645e";
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      var started = false;
      (chartLine.values || []).forEach(function (value, index) {
        if (value === null || !isFinite(value)) { started = false; return; }
        if (!started) { ctx.moveTo(x(index), y(value)); started = true; } else ctx.lineTo(x(index), y(value));
      });
      if (started) ctx.stroke();
    });
    (valleyLines || []).forEach(function (chartLine, lineIndex) {
      ctx.strokeStyle = chartLine.color || ["#ef5350", "#f0a044", "#2962ff"][lineIndex];
      ctx.lineWidth = 1.1;
      ctx.globalAlpha = 0.56;
      ctx.beginPath();
      var valleyStarted = false;
      (chartLine.values || []).forEach(function (value, index) {
        if (value === null || !isFinite(value)) { valleyStarted = false; return; }
        if (!valleyStarted) { ctx.moveTo(x(index), y(value)); valleyStarted = true; } else ctx.lineTo(x(index), y(value));
      });
      if (valleyStarted) ctx.stroke();
      ctx.globalAlpha = 1;
    });
    ctx.fillStyle = "#8a909b"; ctx.textAlign = "left"; ctx.textBaseline = "bottom";
    if (rows[0] && rows[rows.length - 1]) {
      ctx.fillText(String(rows[0].date || "").slice(0, 10), pad.l, height - 8);
      ctx.textAlign = "right";
      ctx.fillText(String(rows[rows.length - 1].date || "").slice(0, 10), width - pad.r, height - 8);
    }
    var last = rows[rows.length - 1];
    [{ key: "close", color: "#4f5665" }, { key: "center", color: "#2962ff" }].forEach(function (item) {
      var value = last[item.key];
      if (value === null || !isFinite(value)) return;
      var label = Number(value).toFixed(2);
      var labelX = width - pad.r - 3;
      var labelY = Math.max(pad.t + 8, Math.min(height - pad.b - 4, y(value)));
      ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      ctx.fillStyle = item.color; ctx.fillText(label, labelX, labelY);
    });
    (valleySignals || []).forEach(function (signal) {
      if (signal.index < 0 || signal.index >= rows.length) return;
      var markerX = x(signal.index);
      var markerY = y(rows[signal.index].close);
      ctx.fillStyle = signal.type === "golden" ? "#d48b00" : "#8d96a6";
      ctx.beginPath(); ctx.arc(markerX, markerY, 3.4, 0, Math.PI * 2); ctx.fill();
      ctx.font = '9px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.fillText(signal.label, markerX, Math.max(pad.t + 12, markerY - 7));
      ctx.textAlign = "left";
    });
    if (last && bias && bias.direction && last.close !== null && last.center !== null) {
      var pullColor = bias.direction === "up" ? "#ef5350" : bias.direction === "down" ? "#089981" : "#8a909b";
      var pullX = Math.max(pad.l + 24, x(rows.length - 1) - 22);
      var fromY = y(last.close);
      var toY = y(last.center);
      ctx.strokeStyle = pullColor; ctx.fillStyle = pullColor; ctx.lineWidth = 2; ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(pullX, fromY); ctx.lineTo(pullX, toY); ctx.stroke(); ctx.setLineDash([]);
      var arrowDirection = toY >= fromY ? 1 : -1;
      ctx.beginPath(); ctx.moveTo(pullX, toY); ctx.lineTo(pullX - 5, toY - arrowDirection * 8); ctx.lineTo(pullX + 5, toY - arrowDirection * 8); ctx.closePath(); ctx.fill();
      ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif'; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      ctx.fillText("回拉 " + (bias.arrow || "→") + " " + Number(bias.valuePct || 0).toFixed(2) + "%", pullX - 8, (fromY + toY) / 2);
      ctx.textAlign = "left";
    }
  }
});
