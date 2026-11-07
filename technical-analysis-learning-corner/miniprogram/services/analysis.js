const config = require("../config");
const demo = require("../data/demo");

var SYMBOL_SUGGESTIONS = [
  { symbol: "sh000001", display: "SH000001", name: "上证指数", type: "中国 · 指数" },
  { symbol: "sz399001", display: "SZ399001", name: "深证成指", type: "中国 · 指数" },
  { symbol: "sz399006", display: "SZ399006", name: "创业板指", type: "中国 · 指数" },
  { symbol: "sh518880", display: "SH518880", name: "黄金ETF", type: "中国 · ETF" },
  { symbol: "hk00700", display: "HK00700", name: "腾讯控股", type: "港股 · 代表资产" },
  { symbol: "us^GSPC", display: "S&P 500", name: "标普500", type: "美国 · 指数" },
  { symbol: "us^IXIC", display: "NASDAQ", name: "纳斯达克综合", type: "美国 · 指数" },
  { symbol: "us^DJI", display: "DOW", name: "道琼斯工业指数", type: "美国 · 指数" },
  { symbol: "usSPY", display: "SPY", name: "标普500 ETF", type: "美国 · ETF" },
  { symbol: "usQQQ", display: "QQQ", name: "纳斯达克100 ETF", type: "美国 · ETF" },
  { symbol: "usGC=F", display: "GOLD", name: "国际金价", type: "国际 · 商品" },
  { symbol: "usCL=F", display: "OIL", name: "国际油价", type: "国际 · 商品" }
];

function normalizeSymbol(value) {
  var raw = String(value || "").trim().toLowerCase().replace(/\s+/g, "");
  if (/^(sh|sz|bj)\d{6}$/.test(raw) || /^hk\d{5}$/.test(raw) || /^us[a-z0-9^=._-]{1,24}$/.test(raw) || /^(comgold|comoil|comsilver)$/.test(raw)) {
    return raw;
  }
  if (/^\d{6}$/.test(raw)) {
    return /^[5689]/.test(raw) ? "sh" + raw : "sz" + raw;
  }
  if (/^\d{5}$/.test(raw)) {
    return "hk" + raw;
  }
  if (/^[a-z][a-z0-9._-]{0,10}$/.test(raw)) return "us" + raw;
  throw new Error("请输入有效代码，例如 sh000001、hk00700、us^GSPC 或 comgold");
}

function codeDistance(left, right) {
  var distance = 0;
  for (var index = 0; index < Math.min(left.length, right.length); index += 1) {
    if (left.charAt(index) !== right.charAt(index)) distance += 1;
  }
  return distance + Math.abs(left.length - right.length);
}

function getSymbolSuggestions(value) {
  var query = String(value || "").trim().toLowerCase().replace(/\s+/g, "");
  if (!query) return SYMBOL_SUGGESTIONS.slice(0, 6);
  var ranked = SYMBOL_SUGGESTIONS.map(function (item, index) {
    var haystack = [item.symbol, item.display, item.name, item.type].join(" ").toLowerCase();
    var score = 999;
    if (haystack === query) score = 0;
    else if (item.symbol.toLowerCase() === query || item.display.toLowerCase() === query) score = 1;
    else if (haystack.indexOf(query) >= 0) score = 2;
    var rawCode = item.symbol.replace(/^(sh|sz|bj|hk)/, "");
    if (/^\d{6}$/.test(query) && /^\d{6}$/.test(rawCode)) {
      var distance = codeDistance(query, rawCode);
      if (distance <= 1) score = Math.min(score, 3 + distance);
    }
    if (query.indexOf("us") === 0 && item.symbol.indexOf("us") === 0) score = Math.min(score, 4);
    return { item: item, score: score, index: index };
  }).filter(function (entry) { return entry.score < 999; });
  ranked.sort(function (left, right) { return left.score - right.score || left.index - right.index; });
  return ranked.slice(0, 6).map(function (entry) { return entry.item; });
}

function buildQuery(params) {
  return Object.keys(params || {}).filter(function (key) {
    return params[key] !== undefined && params[key] !== null && params[key] !== "";
  }).map(function (key) {
    return encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
  }).join("&");
}

function requestApi(path, params, timeout) {
  var query = buildQuery(params);
  var fullPath = path + (query ? "?" + query : "");
  if (config.cloudEnvId && config.cloudServiceName && wx.cloud) {
    return wx.cloud.callContainer({
      config: { env: config.cloudEnvId },
      path: fullPath,
      method: "GET",
      header: { "X-WX-SERVICE": config.cloudServiceName },
      timeout: timeout || 120000
    }).then(function (response) {
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return response.data;
      }
      throw new Error((response.data && response.data.detail) || "云端分析服务暂时不可用");
    });
  }
  if (!config.apiBaseUrl) {
    return Promise.reject(new Error("尚未连接分析服务，请先部署云端接口"));
  }
  return new Promise(function (resolve, reject) {
    wx.request({
      url: config.apiBaseUrl.replace(/\/$/, "") + fullPath,
      method: "GET",
      timeout: timeout || 120000,
      success: function (response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
        } else {
          reject(new Error((response.data && response.data.detail) || "分析服务暂时不可用"));
        }
      },
      fail: function (error) {
        reject(new Error(error.errMsg || "网络请求失败"));
      }
    });
  });
}

function requestAnalysis(symbol) {
  var normalized = normalizeSymbol(symbol);
  if (config.cloudEnvId && config.cloudServiceName && wx.cloud) {
    return wx.cloud.callContainer({
      config: { env: config.cloudEnvId },
      path: "/api/v1/analyze?symbol=" + encodeURIComponent(normalized),
      method: "GET",
      header: {
        "X-WX-SERVICE": config.cloudServiceName
      },
      timeout: 120000
    }).then(function (response) {
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return response.data;
      }
      throw new Error((response.data && response.data.detail) || "云端分析服务暂时不可用");
    });
  }
  if (!config.apiBaseUrl) {
    return Promise.resolve(demo.buildDemo(normalized));
  }
  return new Promise(function (resolve, reject) {
    wx.request({
      url: config.apiBaseUrl.replace(/\/$/, "") + "/api/v1/analyze",
      method: "GET",
      data: { symbol: normalized },
      timeout: 30000,
      success: function (response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
        } else {
          reject(new Error((response.data && response.data.detail) || "分析服务暂时不可用"));
        }
      },
      fail: function (error) {
        reject(new Error(error.errMsg || "网络请求失败"));
      }
    });
  });
}

function requestMovingAverage(symbol, years, minTrades, method, mode) {
  return requestApi("/api/v1/moving-average", {
    symbol: normalizeSymbol(symbol),
    years: years || 3,
    min_trades: minTrades || 5,
    method: method || "single",
    mode: mode || "basic"
  }, 180000);
}

function requestIndicator(symbol, indicator, years) {
  return requestApi("/api/v1/indicators", {
    symbol: normalizeSymbol(symbol),
    indicator: indicator || "macd",
    years: years || 3
  }, 180000);
}

function requestChan(symbol, years) {
  return requestApi("/api/v1/chan", {
    symbol: normalizeSymbol(symbol),
    years: years || 3
  }, 120000);
}

function serviceMode() {
  if (config.cloudEnvId && config.cloudServiceName) {
    return "cloud";
  }
  if (config.apiBaseUrl) {
    return "local";
  }
  return "demo";
}

module.exports = {
  normalizeSymbol: normalizeSymbol,
  getSymbolSuggestions: getSymbolSuggestions,
  requestAnalysis: requestAnalysis,
  requestMovingAverage: requestMovingAverage,
  requestIndicator: requestIndicator,
  requestChan: requestChan,
  serviceMode: serviceMode
};
