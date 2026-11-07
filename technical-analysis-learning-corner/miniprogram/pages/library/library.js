const knowledge = require("../../data/knowledge");

Page({
  data: {
    activeSection: "basics",
    activeCategory: "all",
    keyword: "",
    visibleItems: [],
    sections: [
      { key: "basics", label: "K线基础" },
      { key: "candles", label: "技术形态" },
      { key: "charts", label: "技术图形" },
      { key: "indicators", label: "指标与均线" }
    ],
    categories: [
      { key: "all", label: "全部" },
      { key: "simple", label: "简单形态" },
      { key: "composite", label: "组合形态" },
      { key: "trend", label: "趋势形态" }
    ],
    categoryLabels: {
      simple: "简单形态",
      composite: "组合形态",
      trend: "趋势形态",
      chart: "技术图形"
    },
    sectionInfo: {
      basics: {
        title: "先读懂一根K线",
        copy: "K线用开盘、最高、最低和收盘四个价格记录一个周期。实体表示开盘与收盘之间的结果，上下影线表示盘中试探过但未能保持的范围。",
        rule: "单根K线只描述一个周期。方向判断必须结合前置趋势、关键价位和后续确认。"
      },
      candles: {
        title: "什么是技术形态",
        copy: "技术形态是由一根到数根K线的实体、影线、顺序和相对位置构成的局部价格语言，可分为简单、组合和趋势形态。",
        rule: "反转形态必须位于趋势末端；互相矛盾的形态不能在同一区间同时成立；没有确认时只称为线索。"
      },
      charts: {
        title: "什么是技术图形",
        copy: "技术图形是更长时间里由高点、低点和价格边界组成的轮廓，常见形状包括山峰、岛屿、旗帜、三角形和楔形。它描述的是价格结构，不是单根K线。",
        rule: "先画支撑、阻力或颈线，再等待突破、跌破与回踩确认。图中买卖点表示确认后的参考位置，不是提前预测。"
      },
      indicators: {
        title: "先理解工具，再看参数",
        copy: "均线和技术指标把价格、波动或成交信息换成更容易比较的线。参数只是观察窗口，不存在适合所有市场的万能数字。",
        rule: "先看指标解决什么问题，再看参数和图表。历史最优只表示过去表现较好，不是未来收益保证。"
      }
    },
    currentInfo: null
  },

  onLoad: function () {
    this.refresh();
  },

  changeSection: function (event) {
    this.setData({
      activeSection: event.currentTarget.dataset.key,
      activeCategory: "all",
      keyword: ""
    });
    this.refresh();
  },

  changeCategory: function (event) {
    this.setData({ activeCategory: event.currentTarget.dataset.key });
    this.refresh();
  },

  handleSearch: function (event) {
    this.setData({ keyword: event.detail.value });
    this.refresh();
  },

  refresh: function () {
    var section = this.data.activeSection;
    var items = section === "basics"
      ? knowledge.basics()
      : section === "charts"
        ? knowledge.chartPatterns()
        : section === "indicators"
          ? knowledge.indicators()
          : knowledge.candlePatterns();
    var category = this.data.activeCategory;
    var keyword = String(this.data.keyword || "").trim().toLowerCase();
    if (section === "candles" && category !== "all") {
      items = items.filter(function (item) {
        return item.category === category;
      });
    }
    if (keyword) {
      items = items.filter(function (item) {
        return [
          item.name,
          item.displayName,
          item.definition,
          item.meaning,
          item.confirmation,
          item.remember,
          item.parameters,
          item.source
        ].join(" ").toLowerCase().indexOf(keyword) >= 0;
      });
    }
    this.setData({
      visibleItems: items,
      currentInfo: this.data.sectionInfo[section]
    });
  }
});
