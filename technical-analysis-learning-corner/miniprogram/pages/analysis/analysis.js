const knowledge = require("../../data/knowledge");
const patternDisplay = require("../../utils/pattern-display");

Page({
  data: {
    analysis: null,
    activePeriod: "M",
    activeLabel: "月线",
    currentPeriod: null,
    visiblePatterns: [],
    patternDisplaySummary: {
      visibleTotal: 0,
      canvasTotal: 0,
      totalsByCategory: {}
    },
    importantOnly: true,
    readingMode: "objective",
    detailVisible: false,
    selectedEvent: null,
    layerAudit: null,
    periodTabs: [
      { key: "M", label: "月线" },
      { key: "W", label: "周线" },
      { key: "D", label: "日线" }
    ],
    layerOptions: [
      { key: "simple", label: "简单形态" },
      { key: "composite", label: "组合形态" },
      { key: "trend", label: "趋势形态" },
      { key: "chart", label: "技术图形" },
      { key: "gap", label: "缺口" },
      { key: "zigzag", label: "主要波段" },
      { key: "trendline", label: "趋势线" },
      { key: "ma", label: "长期均线" },
      { key: "support", label: "支撑位" },
      { key: "resistance", label: "阻力位" }
    ],
    visibility: {
      simple: false,
      composite: false,
      trend: false,
      chart: false,
      gap: false,
      zigzag: false,
      trendline: false,
      ma: false,
      support: false,
      resistance: false
    },
    eventVisibility: {},
    categoryLabels: {
      simple: "简单形态",
      composite: "组合形态",
      trend: "趋势形态",
      chart: "技术图形",
      gap: "缺口"
    },
    graphicExplanations: {
      zigzag: "连接主要高低拐点，用于观察主升、调整和主跌波段。",
      trendline: "连接有意义的高点或低点，突破或跌破后提示结构变化。",
      support: "价格回落时可能出现承接的观察区域，不是绝对底线。",
      resistance: "价格上行时可能遇到抛压的观察区域，不是绝对上限。"
    }
  },

  onLoad: function () {
    var analysis = getApp().globalData.analysis;
    if (!analysis) {
      return;
    }
    var prepared = this.preparePeriod(analysis.periods.M);
    this.setData(Object.assign({
      analysis: analysis,
      currentPeriod: prepared
    }, this.derivePatternDisplay(prepared)));
  },

  preparePeriod: function (period) {
    if (!period) {
      return period;
    }
    var legacyPatterns = period.patterns || [];
    var faeDisplay = period.fae && period.fae.display ? period.fae.display : null;
    var faeDefault = faeDisplay && Array.isArray(faeDisplay.default)
      ? faeDisplay.default
      : [];
    var faeManual = [];
    if (faeDisplay && faeDisplay.manual_layers) {
      ["chart", "trend", "combination", "simple", "gap"].forEach(function (kind) {
        var values = faeDisplay.manual_layers[kind];
        if (Array.isArray(values)) {
          faeManual = faeManual.concat(values);
        }
      });
    }
    var signalKey = function (item) {
      var rawDirection = item.direction_short || item.direction || "neutral";
      return [
        item.pattern_id || item.pattern || item.name || "unknown",
        Number(item.start || 0),
        Number(item.end !== undefined ? item.end : item.start || 0),
        String(rawDirection)
      ].join(":");
    };
    var legacyByKey = {};
    legacyPatterns.forEach(function (item) {
      legacyByKey[signalKey(item)] = item;
    });
    var mapSignal = function (item, index, autoSelected, manualAvailable) {
          var legacy = legacyByKey[signalKey(item)] || (autoSelected ? legacyPatterns[index] : null) || {};
          var registryCategory = String(item.registry_category || "");
          var kind = String(item.kind || item.category || "simple");
          var category = registryCategory === "gap"
            ? "gap"
            : kind === "combination"
              ? "composite"
              : ["simple", "trend", "chart", "gap"].indexOf(kind) >= 0
                ? kind
                : "simple";
          var direction = item.direction_short || item.direction || "neutral";
          if (direction === "bullish") direction = "bull";
          if (direction === "bearish") direction = "bear";
          return Object.assign({}, legacy, item, {
            id: legacy.id || ["fae", item.period || "P", signalKey(item)].join("-"),
            category: category,
            direction: direction,
            important: autoSelected,
            autoSelected: autoSelected,
            manualAvailable: manualAvailable
          });
        };
    var autoPatterns = faeDisplay
      ? faeDefault.map(function (item, index) {
          return mapSignal(item, index, true, false);
        })
      : legacyPatterns.map(function (item) {
          return Object.assign({}, item, {
            autoSelected: true,
            manualAvailable: true,
            important: item.important !== false
          });
        });
    var manualPatterns = faeDisplay
      ? faeManual.map(function (item, index) {
          return mapSignal(item, index, false, true);
        })
      : legacyPatterns.map(function (item) {
          return Object.assign({}, item, {
            autoSelected: true,
            manualAvailable: true
          });
        });
    var pooledByKey = {};
    var rawPatterns = [];
    var addPattern = function (item) {
      var key = signalKey(item);
      var existing = pooledByKey[key];
      if (existing) {
        var autoSelected = existing.autoSelected === true || item.autoSelected === true;
        Object.assign(existing, item, {
          id: existing.id || item.id,
          autoSelected: autoSelected,
          manualAvailable: existing.manualAvailable === true || item.manualAvailable === true,
          important: autoSelected
        });
        return;
      }
      pooledByKey[key] = item;
      rawPatterns.push(item);
    };
    autoPatterns.forEach(addPattern);
    manualPatterns.forEach(addPattern);
    var seen = {};
    var sourcePatterns = rawPatterns.filter(function (item) {
      var key = signalKey(item);
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    }).map(function (item) {
      var entry = knowledge.getKnowledge(item.name, item.category, item.direction);
      return Object.assign({}, item, {
        displayName: entry.displayName || entry.name || item.name,
        definition: item.definition || entry.definition,
        meaning: item.meaning || entry.meaning,
        confirmation: item.confirmation || entry.confirmation
      });
    });
    var manualCount = sourcePatterns.filter(function (item) {
      return item.manualAvailable === true;
    }).length;
    var importantCount = sourcePatterns.filter(function (item) {
      return item.autoSelected === true;
    }).length;
    return Object.assign({}, period, {
      patterns: sourcePatterns,
      faeConnected: Boolean(faeDisplay),
      totalPatternCount: manualCount,
      importantPatternCount: importantCount
    });
  },

  derivePatternDisplay: function (period) {
    if (!period) {
      return {
        visiblePatterns: [],
        patternDisplaySummary: { visibleTotal: 0, canvasTotal: 0, totalsByCategory: {} }
      };
    }
    var listSelection = patternDisplay.selectForCanvas(period.patterns || [], {
      visibility: this.data.visibility,
      autoIdentify: this.data.importantOnly,
      eventVisibility: {}
    });
    var canvasSelection = patternDisplay.selectForCanvas(period.patterns || [], {
      visibility: this.data.visibility,
      autoIdentify: this.data.importantOnly,
      eventVisibility: this.data.eventVisibility
    });
    var visiblePatterns = listSelection.visible.slice().sort(function (left, right) {
      return Number(right.end || 0) - Number(left.end || 0);
    });
    return {
      visiblePatterns: visiblePatterns,
      patternDisplaySummary: {
        visibleTotal: listSelection.visibleTotal,
        canvasTotal: canvasSelection.canvasTotal,
        totalsByCategory: listSelection.totalsByCategory
      }
    };
  },

  refreshPatternDisplay: function () {
    this.setData(this.derivePatternDisplay(this.data.currentPeriod));
  },

  changePeriod: function (event) {
    var key = event.currentTarget.dataset.period;
    var labels = { M: "月线", W: "周线", D: "日线" };
    var prepared = this.preparePeriod(this.data.analysis.periods[key]);
    this.setData(Object.assign({
      activePeriod: key,
      activeLabel: labels[key],
      currentPeriod: prepared,
      detailVisible: false,
      selectedEvent: null
    }, this.derivePatternDisplay(prepared)));
  },

  toggleLayer: function (event) {
    var key = event.currentTarget.dataset.key;
    var path = "visibility." + key;
    var changes = {};
    changes[path] = event.detail.value;
    var page = this;
    this.setData(changes, function () {
      page.refreshPatternDisplay();
    });
  },

  toggleImportant: function (event) {
    var page = this;
    this.setData({ importantOnly: event.detail.value }, function () {
      page.refreshPatternDisplay();
    });
  },

    captureLayerAudit: function () {
    var chart = this.selectComponent("#analysisKlineChart");
    var audit = chart && chart.getLayerDrawAudit ? chart.getLayerDrawAudit() : null;
    this.setData({ layerAudit: audit });
      return audit;
    },

    captureChartAudit: function () {
      var chart = this.selectComponent("#analysisKlineChart");
      return {
        layers: chart && chart.getLayerDrawAudit ? chart.getLayerDrawAudit() : null,
        labels: chart && chart.getLabelLayoutAudit ? chart.getLabelLayoutAudit() : null,
        layout: chart && chart.getLayoutAudit ? chart.getLayoutAudit() : null,
        display: Object.assign({}, this.data.patternDisplaySummary)
      };
    },

  toggleEvent: function (event) {
    var id = event.currentTarget.dataset.id;
    var path = "eventVisibility." + id;
    var changes = {};
    changes[path] = event.detail.value;
    var page = this;
    this.setData(changes, function () {
      page.refreshPatternDisplay();
    });
  },

  changeReadingMode: function (event) {
    this.setData({ readingMode: event.currentTarget.dataset.mode });
  },

  openEvent: function (event) {
    var item = this.data.visiblePatterns[event.currentTarget.dataset.index];
    this.setData({
      selectedEvent: item,
      detailVisible: true
    });
  },

  closeEvent: function () {
    this.setData({
      detailVisible: false,
      selectedEvent: null
    });
  },

  stopPropagation: function () {},

  backHome: function () {
    wx.switchTab({ url: "/pages/index/index" });
  }
});
