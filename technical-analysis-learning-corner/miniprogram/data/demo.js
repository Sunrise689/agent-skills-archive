const knowledge = require("./knowledge");

function round(value) {
  return Math.round(value * 100) / 100;
}

function createBars(period, count, seed, base, drift) {
  var bars = [];
  var price = base;
  var start = new Date(Date.UTC(period === "M" ? 2019 : 2025, 0, 3));
  for (var index = 0; index < count; index += 1) {
    var wave = Math.sin((index + seed) * 0.43) * 0.011;
    var pulse = Math.cos((index + seed) * 0.17) * 0.006;
    var lateMove = index > count * 0.72 ? drift * 0.55 : 0;
    var move = drift + wave + pulse + lateMove;
    var open = price * (1 + Math.sin(index * 0.71) * 0.003);
    var close = price * (1 + move);
    var spread = Math.max(price * (0.008 + Math.abs(wave) * 0.5), 0.08);
    var high = Math.max(open, close) + spread;
    var low = Math.min(open, close) - spread * (0.8 + (index % 4) * 0.08);
    var date = new Date(start.getTime());
    if (period === "D") {
      date.setUTCDate(start.getUTCDate() + index);
    } else if (period === "W") {
      date.setUTCDate(start.getUTCDate() + index * 7);
    } else {
      date.setUTCMonth(start.getUTCMonth() + index);
    }
    bars.push({
      date: date.toISOString().slice(0, 10),
      open: round(open),
      high: round(high),
      low: round(low),
      close: round(close),
      ma: null
    });
    price = close;
  }
  var maWindow = period === "D" ? 24 : 12;
  bars.forEach(function (bar, index) {
    if (index < maWindow - 1) {
      return;
    }
    var windowBars = bars.slice(index - maWindow + 1, index + 1);
    bar.ma = round(windowBars.reduce(function (sum, item) {
      return sum + item.close;
    }, 0) / maWindow);
  });
  return bars;
}

function event(id, name, category, direction, start, end, state, important) {
  var entry = knowledge.getKnowledge(name, category, direction);
  return {
    id: id,
    name: name,
    category: category,
    direction: direction,
    start: start,
    end: end,
    confidenceLabel: "高",
    important: important !== false,
    state: state,
    definition: entry.definition,
    meaning: entry.meaning,
    confirmation: entry.confirmation
  };
}

function periodData(period, bars, direction, patterns) {
  var last = bars[bars.length - 1];
  var recent = bars.slice(-18);
  var support = Math.min.apply(null, recent.map(function (bar) { return bar.low; }));
  var resistance = Math.max.apply(null, recent.map(function (bar) { return bar.high; }));
  var pivots = [];
  for (var i = 5; i < bars.length - 4; i += 7) {
    var local = bars.slice(Math.max(0, i - 3), Math.min(bars.length, i + 4));
    var high = Math.max.apply(null, local.map(function (bar) { return bar.high; }));
    var low = Math.min.apply(null, local.map(function (bar) { return bar.low; }));
    if (bars[i].high >= high) {
      pivots.push({ index: i, price: bars[i].high, kind: "high" });
    } else if (bars[i].low <= low) {
      pivots.push({ index: i, price: bars[i].low, kind: "low" });
    }
  }
  pivots = pivots.slice(-7);
  return {
    direction: direction,
    stage: direction === "上升趋势" ? "价格重心仍在抬高" : "价格重心仍在下移",
    support: round(support),
    resistance: round(resistance),
    latest: last.close,
    objectiveSummary: "当前" + direction + "。支撑 " + round(support) + "，阻力 " + round(resistance) + "；先看价格是否守住或突破这些位置。",
    ruleSummary: period === "M"
      ? "月线决定主要方向。小周期出现反弹，也应先按长期结构中的修复理解。"
      : period === "W"
        ? "周线用于观察中期力度。组合形态只有在正确位置并获得后续确认时才成立。"
        : "日线用于寻找执行点。趋势形态与缺口需要结合月线、周线方向使用。",
    bars: bars,
    patterns: patterns,
    graphics: [
      {
        id: period + "-zigzag",
        type: "zigzag",
        name: "主要波段",
        points: pivots
      },
      {
        id: period + "-support",
        type: "support",
        name: "支撑位",
        price: round(support)
      },
      {
        id: period + "-resistance",
        type: "resistance",
        name: "阻力位",
        price: round(resistance)
      },
      {
        id: period + "-trendline",
        type: "trendline",
        name: direction === "上升趋势" ? "上升趋势线" : "下降趋势线",
        direction: direction === "上升趋势" ? "bull" : "bear",
        points: pivots.slice(-3)
      }
    ]
  };
}

function buildDemo(symbol) {
  var monthly = createBars("M", 62, 3, 3.08, 0.008);
  var weekly = createBars("W", 78, 7, 4.12, 0.0035);
  var daily = createBars("D", 86, 11, 5.02, -0.0018);
  var periods = {
    M: periodData("M", monthly, "上升趋势", [
      event("m-engulf", "看涨吞没", "simple", "bull", 27, 28, "低位反攻，已获后续上涨确认"),
      event("m-star", "射击之星", "simple", "bear", 55, 55, "高位压力，等待月线确认"),
      event("m-doji", "十字星", "simple", "neutral", 48, 48, "普通犹豫线索", false)
    ]),
    W: periodData("W", weekly, "上升趋势", [
      event("w-soldiers", "红三兵", "composite", "bull", 42, 44, "买方连续推进"),
      event("w-triangle", "上升三角形", "chart", "bull", 47, 63, "阻力保持水平，支撑逐步抬高"),
      event("w-island", "岛形顶", "composite", "bear", 67, 70, "反转警报，需观察缺口"),
      event("w-gap", "下降缺口", "gap", "bear", 70, 71, "未回补，构成上方压力"),
      event("w-doji", "十字星", "simple", "neutral", 58, 58, "局部犹豫线索", false)
    ]),
    D: periodData("D", daily, "下降趋势", [
      event("d-double-top", "双顶", "chart", "bear", 28, 48, "两次冲高受阻，重点观察颈线"),
      event("d-decline", "绵绵阴跌", "trend", "bear", 61, 83, "高低点缓慢下移"),
      event("d-gap", "下降缺口", "gap", "bear", 72, 73, "已回补，反抽力度仍弱"),
      event("d-spinning", "螺旋桨", "simple", "neutral", 76, 76, "普通波动线索", false)
    ])
  };
  var latest = daily[daily.length - 1];
  var previous = daily[daily.length - 2];
  return {
    source: "demo",
    symbol: String(symbol || "sh518880").toUpperCase(),
    name: String(symbol || "sh518880").toLowerCase() === "sh518880" ? "黄金ETF" : "示例资产",
    updatedAt: latest.date,
    latest: latest.close,
    changePct: round((latest.close / previous.close - 1) * 100),
    overview: "月线保持上升，周线仍有中期支撑，日线处于回调。大周期没有转坏前，日线弱势先按上升结构中的调整观察；执行上等待日线重新站回阻力位。",
    periods: periods
  };
}

module.exports = {
  buildDemo: buildDemo
};
