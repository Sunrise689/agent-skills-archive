const service = require("../../services/analysis");

Page({
  data: { symbol: "sh000001", years: 5, yearsList: [1, 2, 3, 5, 10], loading: false, result: null, symbolSuggestions: [] },
  handleInput: function (event) {
    var value = event.detail.value;
    this.setData({ symbol: value, symbolSuggestions: service.getSymbolSuggestions(value) });
  },
  selectSymbolSuggestion: function (event) {
    this.setData({ symbol: event.currentTarget.dataset.symbol, symbolSuggestions: [] });
  },
  selectYears: function (event) { this.setData({ years: Number(event.currentTarget.dataset.value) }); },
  run: function () {
    var page = this;
    if (this.data.loading) return;
    this.setData({ loading: true, symbolSuggestions: [] });
    service.requestChan(this.data.symbol, this.data.years).then(function (result) {
      page.setData({ loading: false, result: result }, function () { page.drawChart(); });
    }).catch(function (error) {
      page.setData({ loading: false });
      wx.showModal({ title: "暂时无法计算", content: error.message || "请稍后重试", showCancel: false });
    });
  },
  drawChart: function () {
    var page = this;
    setTimeout(function () {
      wx.createSelectorQuery().in(page).select("#chanCanvas").fields({ node: true, size: true }).exec(function (items) {
        if (!items || !items[0] || !items[0].node) return;
        var canvas = items[0].node, width = items[0].width, height = items[0].height;
        var info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        var ratio = info.pixelRatio || 1;
        canvas.width = width * ratio; canvas.height = height * ratio;
        var ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio);
        page.renderChart(ctx, width, height, page.data.result || {});
      });
    }, 60);
  },
  renderChart: function (ctx, width, height, result) {
    var pivots = result.pivots || [], centers = result.centers || [], signals = result.signals || [];
    ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, width, height);
    if (!pivots.length) return;
    var pad = { l: 18, r: 18, t: 20, b: 26 };
    var prices = pivots.map(function (item) { return Number(item.price); });
    centers.forEach(function (item) { prices.push(Number(item.low), Number(item.high)); });
    var min = Math.min.apply(null, prices), max = Math.max.apply(null, prices), span = Math.max(max - min, 1e-6); min -= span * .1; max += span * .1;
    var firstIndex = Number(pivots[0].index), lastIndex = Number(pivots[pivots.length - 1].index), indexSpan = Math.max(lastIndex - firstIndex, 1);
    var x = function (index) { return pad.l + (Number(index) - firstIndex) * (width - pad.l - pad.r) / indexSpan; };
    var y = function (price) { return pad.t + (max - Number(price)) * (height - pad.t - pad.b) / (max - min); };
    ctx.strokeStyle = "#edf0f4"; ctx.lineWidth = 1; ctx.setLineDash([3, 5]);
    for (var g = 1; g < 5; g += 1) { var gy = pad.t + g * (height - pad.t - pad.b) / 5; ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(width - pad.r, gy); ctx.stroke(); }
    ctx.setLineDash([]);
    centers.forEach(function (center) {
      var left = Math.max(pad.l, x(center.startIndex)), right = Math.min(width - pad.r, x(center.endIndex));
      var top = y(center.high), bottom = y(center.low);
      ctx.fillStyle = "rgba(41,98,255,.08)"; ctx.strokeStyle = "rgba(41,98,255,.56)"; ctx.lineWidth = 1;
      ctx.fillRect(left, top, Math.max(right - left, 4), bottom - top); ctx.strokeRect(left, top, Math.max(right - left, 4), bottom - top);
    });
    ctx.strokeStyle = "#20242d"; ctx.lineWidth = 2.2; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.beginPath();
    pivots.forEach(function (item, index) { if (index === 0) ctx.moveTo(x(item.index), y(item.price)); else ctx.lineTo(x(item.index), y(item.price)); }); ctx.stroke();
    pivots.forEach(function (item) { ctx.fillStyle = item.kind === "bottom" ? "#f23645" : "#089981"; ctx.beginPath(); ctx.arc(x(item.index), y(item.price), 2.6, 0, Math.PI * 2); ctx.fill(); });
    ctx.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif';
    signals.forEach(function (item) {
      var px = x(item.index), py = y(item.price), isBuy = item.type === "buy";
      ctx.fillStyle = isBuy ? "#f23645" : "#089981"; ctx.beginPath(); ctx.arc(px, py, 4.2, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = isBuy ? "#c82030" : "#067c69"; ctx.fillText(item.label, Math.min(px + 6, width - 58), py + (isBuy ? 14 : -8));
    });
  }
});
