const analysisService = require("../../services/analysis");

Page({
  data: {
    symbol: "sh000001",
    loading: false,
    loadingQuoteIndex: 0,
    analysisQuotes: [
      { text: "看清趋势再做决定。", en: "Read the trend first, then make your move.", source: "— 来自于网络" },
      { text: "真正的交易者需要买入、卖出，也需要等待。", en: "A real trader needs to buy, sell, and wait.", source: "— 来自于网络" },
      { text: "价格沿着阻力最小的方向运行。", en: "Price tends to move along the path of least resistance.", source: "— 来自于网络" },
      { text: "先保护本金，再谈收益。", en: "Protect capital first; returns come second.", source: "— 来自于网络" }
    ],
    demoMode: false,
    inputFocused: false,
    symbolSuggestions: [],
    sourceLabel: "本机真实行情",
    quickSymbols: [
      { symbol: "sh000001", display: "SH000001", name: "上证指数", type: "中国 · 指数", short: "SH", tone: "blue" },
      { symbol: "sz399001", display: "SZ399001", name: "深证成指", type: "中国 · 指数", short: "SZ", tone: "blue" },
      { symbol: "sz399006", display: "SZ399006", name: "创业板指", type: "中国 · 指数", short: "CY", tone: "green" },
      { symbol: "us^GSPC", display: "S&P 500", name: "标普500", type: "美国 · 指数", short: "SP", tone: "blue" },
      { symbol: "us^IXIC", display: "NASDAQ", name: "纳斯达克综合", type: "美国 · 指数", short: "NQ", tone: "green" },
      { symbol: "usGC=F", display: "GOLD", name: "国际金价", type: "国际 · 商品", short: "Au", tone: "gold" },
      { symbol: "usCL=F", display: "OIL", name: "国际油价", type: "国际 · 商品", short: "Oi", tone: "gold" }
    ]
  },

  onLoad: function (options) {
    this.setData({ inputFocused: options && options.focus === "1" });
  },

  onReady: function () {
    this.drawHeroChart();
  },

  onShow: function () {
    var mode = analysisService.serviceMode();
    this.setData({
      demoMode: mode === "demo",
      sourceLabel: mode === "cloud" ? "云端真实行情" : mode === "local" ? "本机真实行情" : "内置演示数据"
    });
    this.drawHeroChart();
  },

  onHide: function () {
    clearInterval(this.quoteTimer);
  },

  handleInput: function (event) {
    var value = event.detail.value;
    this.setData({ symbol: value, symbolSuggestions: analysisService.getSymbolSuggestions(value) });
  },

  selectSymbolSuggestion: function (event) {
    this.setData({ symbol: event.currentTarget.dataset.symbol, symbolSuggestions: [] });
  },

  startQuickAnalysis: function (event) {
    var page = this;
    this.setData({ symbol: event.currentTarget.dataset.symbol, symbolSuggestions: [] }, function () {
      page.startAnalysis();
    });
  },

  drawHeroChart: function () {
    var page = this;
    clearTimeout(this.chartTimer);
    this.chartTimer = setTimeout(function () {
      wx.createSelectorQuery().in(page).select("#heroCanvas").fields({ node: true, size: true }).exec(function (result) {
        if (!result || !result[0] || !result[0].node) return;
        var canvas = result[0].node;
        var width = result[0].width;
        var height = result[0].height;
        var info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        var ratio = info.pixelRatio || 1;
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        var context = canvas.getContext("2d");
        context.scale(ratio, ratio);
        page.renderHeroChart(context, width, height);
      });
    }, 60);
  },

  renderHeroChart: function (context, width, height) {
    var red = "#ef5350";
    var green = "#26a69a";
    var grid = "#edf0f4";
    var candles = [
      [72, 65, 79, 60], [66, 70, 74, 62], [69, 61, 72, 57], [60, 67, 71, 56],
      [66, 77, 81, 63], [76, 72, 82, 68], [73, 82, 86, 70], [81, 89, 94, 78],
      [88, 84, 95, 80], [85, 94, 99, 82], [93, 88, 98, 84], [89, 101, 106, 86]
    ];
    var left = 8;
    var right = width - 8;
    var top = 12;
    var bottom = height - 12;
    var min = 52;
    var max = 108;
    var yAt = function (value) { return bottom - ((value - min) / (max - min)) * (bottom - top); };
    var slot = (right - left) / candles.length;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    for (var gridIndex = 1; gridIndex < 4; gridIndex += 1) {
      var gridY = top + ((bottom - top) * gridIndex) / 4;
      context.strokeStyle = grid;
      context.setLineDash([3, 5]);
      context.beginPath();
      context.moveTo(left, gridY);
      context.lineTo(right, gridY);
      context.stroke();
    }
    context.setLineDash([]);
    var ma = [66, 65, 64, 65, 68, 71, 75, 79, 82, 85, 88, 91];
    context.strokeStyle = "#1a237e";
    context.lineWidth = 1.7;
    context.beginPath();
    ma.forEach(function (value, index) {
      var x = left + slot * (index + 0.5);
      var y = yAt(value);
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.stroke();
    candles.forEach(function (bar, index) {
      var x = left + slot * (index + 0.5);
      var openY = yAt(bar[0]);
      var closeY = yAt(bar[1]);
      var color = bar[1] >= bar[0] ? red : green;
      context.strokeStyle = color;
      context.fillStyle = color;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x, yAt(bar[2]));
      context.lineTo(x, yAt(bar[3]));
      context.stroke();
      context.fillRect(x - Math.max(4, Math.min(9, slot * 0.5)) / 2, Math.min(openY, closeY), Math.max(4, Math.min(9, slot * 0.5)), Math.max(2, Math.abs(closeY - openY)));
    });
    var supportY = yAt(64);
    context.strokeStyle = "rgba(38, 166, 154, 0.68)";
    context.setLineDash([6, 4]);
    context.beginPath();
    context.moveTo(left + slot * 1.2, supportY);
    context.lineTo(right, supportY);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = "#9a9da6";
    context.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif';
    context.fillText("支撑", left + slot * 1.3, supportY - 5);
  },

  onUnload: function () {
    clearInterval(this.quoteTimer);
    clearTimeout(this.chartTimer);
  },

  startAnalysis: function () {
    var page = this;
    if (this.data.loading) return;
    this.setData({ loading: true, loadingQuoteIndex: 0, symbolSuggestions: [] });
    clearInterval(this.quoteTimer);
    this.quoteTimer = setInterval(function () {
      page.setData({ loadingQuoteIndex: (page.data.loadingQuoteIndex + 1) % page.data.analysisQuotes.length });
    }, 2600);
    analysisService.requestAnalysis(this.data.symbol).then(function (result) {
      getApp().globalData.analysis = result;
      clearInterval(page.quoteTimer);
      page.setData({ loading: false });
      wx.navigateTo({ url: "/pages/analysis/analysis" });
    }).catch(function (error) {
      clearInterval(page.quoteTimer);
      page.setData({ loading: false });
      wx.showModal({ title: "暂时无法分析", content: error.message || "请检查代码后重试", showCancel: false });
    });
  }
});
