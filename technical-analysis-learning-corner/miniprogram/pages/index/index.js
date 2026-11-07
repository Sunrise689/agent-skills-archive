Page({
  data: {
    analysisTools: [
      {
        key: "chart",
        title: "图表分析",
        subtitle: "趋势、形态与关键价位",
        status: "available",
        statusText: "可使用",
        icon: "chart"
      },
      {
        key: "ma",
        title: "均线无忧",
        subtitle: "自动寻找最优移动平均线",
        status: "available",
        statusText: "可使用",
        icon: "ma"
      },
      {
        key: "indicator",
        title: "指标大师",
        subtitle: "拟合常见技术指标最优参数",
        status: "available",
        statusText: "可使用",
        icon: "indicator"
      },
      {
        key: "chan",
        title: "缠中说禅",
        subtitle: "缠论结构与笔、线段分析",
        status: "available",
        statusText: "可使用",
        icon: "chan"
      }
    ],
    quoteIndex: 0,
    marketQuotes: [
      { id: "q01", text: "在别人贪婪时恐惧，在别人恐惧时贪婪。", en: "Be fearful when others are greedy, and greedy when others are fearful.", source: "— 沃伦·巴菲特" },
      { id: "q02", text: "市场短期是投票机，长期是称重机。", en: "In the short run, the market is a voting machine; in the long run, a weighing machine.", source: "— 本杰明·格雷厄姆" },
      { id: "q03", text: "买入一项资产前，先做足功课；热闹不能替代研究。", en: "Do your homework before you buy; excitement is no substitute for research.", source: "— 彼得·林奇" },
      { id: "q04", text: "市场关注的不只是基本面，而是基本面的边际变化。", en: "Markets respond not only to fundamentals, but to changes at the margin.", source: "— 乔治·索罗斯" },
      { id: "q05", text: "你不能预测市场，但可以为不同情形做好准备。", en: "You cannot predict the market, but you can prepare for different outcomes.", source: "— 霍华德·马克斯" },
      { id: "q06", text: "看清趋势再做决定。", en: "Read the trend first, then make your move.", source: "— 来自于网络" },
      { id: "q07", text: "真正的交易者，做的事只有三件：买入、卖出、等待。", en: "A real trader knows when to buy, when to sell, and when to wait.", source: "— 来自于网络" },
      { id: "q08", text: "价格偏离均线后，终会寻找回归趋势的路径。", en: "When price moves far from its moving average, it may seek a path back toward the trend.", source: "— 约瑟夫·格兰维尔" },
      { id: "q09", text: "技术分析不是预测，而是辨认趋势的方向。", en: "Technical analysis is not prediction; it is the study of trend direction.", source: "— J. Welles Wilder" },
      { id: "q10", text: "趋势是朋友，直到趋势改变。", en: "The trend is your friend until it changes.", source: "— 来自于网络" },
      { id: "q11", text: "缩短亏损，让利润奔跑。", en: "Cut losses short and let profits run.", source: "— 来自于网络" },
      { id: "q12", kind: "contact", text: "当前为免费版本，欢迎提交详细反馈；付费版上线后将随机赠送永久免费使用资格。", en: "Free for now; detailed feedback may be rewarded with permanent access later.", source: "— 意见反馈 / 商务合作" }
    ]
  },

  selectAnalysisTool: function (event) {
    var key = event.currentTarget.dataset.key;
    if (key === "chart") {
      wx.navigateTo({ url: "/pages/chart/chart" });
      return;
    }
    if (key === "ma") {
      wx.navigateTo({ url: "/pages/sma/sma" });
      return;
    }
    if (key === "indicator") {
      wx.navigateTo({ url: "/pages/indicator/indicator" });
      return;
    }
    if (key === "chan") {
      wx.navigateTo({ url: "/pages/chan/chan" });
      return;
    }
    wx.showToast({ title: "功能正在开发中", icon: "none" });
  },

  focusAnalysisSearch: function () {
    wx.navigateTo({ url: "/pages/chart/chart?focus=1" });
  },

  handleQuoteChange: function (event) {
    var index = Number(event.detail.current) || 0;
    this.setData({ quoteIndex: index });
  },

  handleQuoteTap: function (event) {
    if (event.currentTarget.dataset.kind === "contact") {
      wx.navigateTo({ url: "/pages/contact/contact" });
    }
  }
});
