const patternDisplay = require("../../utils/pattern-display");

const CHART_FONT_FAMILY = '"DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif';
const MAX_CANVAS_WIDTH = 2600;
const LATEST_VIEWPORT_GUTTER = 56;

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  return Object.keys(value)
    .filter(function (key) { return /^\d+$/.test(key); })
    .sort(function (left, right) { return Number(left) - Number(right); })
    .map(function (key) { return value[key]; });
}

function normalizePeriod(period) {
  if (!period || typeof period !== "object") return period;
  return Object.assign({}, period, {
    bars: asArray(period.bars),
    patterns: asArray(period.patterns),
    graphics: asArray(period.graphics)
  });
}

function chartFont(size, weight) {
  return (weight ? weight + " " : "") + size + "px " + CHART_FONT_FAMILY;
}

Component({
  properties: {
    period: {
      type: Object,
      value: null,
      observer: "scheduleDraw"
    },
    visibility: {
      type: Object,
      value: {},
      observer: "scheduleDraw"
    },
    eventVisibility: {
      type: Object,
      value: {},
      observer: "scheduleDraw"
    },
    autoIdentify: {
      type: Boolean,
      value: true,
      observer: "scheduleDraw"
    }
  },

  data: {
    selectedBar: null,
    canvasWidth: 320,
    viewportWidth: 320,
    scrollLeft: 0
  },

  lifetimes: {
    ready: function () {
      this.scheduleDraw();
    },
    detached: function () {
      clearTimeout(this.drawTimer);
      clearTimeout(this.scrollTimer);
    }
  },

  methods: {
    scheduleDraw: function () {
      var component = this;
      clearTimeout(this.drawTimer);
      this.drawTimer = setTimeout(function () {
        component.draw();
      }, 40);
    },

    getPeriodSignature: function (period) {
      period = normalizePeriod(period);
      var bars = period && period.bars || [];
      var first = bars[0] && bars[0].date || "";
      var last = bars[bars.length - 1] && bars[bars.length - 1].date || "";
      return [period && period.period || "", period && period.displayMode || "", bars.length, first, last].join("|");
    },

    calculateCanvasWidth: function (viewportWidth, period) {
      var safeViewport = Math.max(280, Number(viewportWidth) || 320);
      period = normalizePeriod(period);
      var bars = period && period.bars || [];
      if (!bars.length) return safeViewport;
      var selection = patternDisplay.selectForCanvas(period.patterns || [], {
        visibility: this.data.visibility,
        autoIdentify: this.data.autoIdentify,
        eventVisibility: this.data.eventVisibility
      });
      var slot = period.displayMode === "trend" ? 7.5 : 8.5;
      if (selection.visibleTotal > 8) slot += 1.5;
      if (selection.visibleTotal > 16) slot += 1;
      return Math.min(MAX_CANVAS_WIDTH, Math.max(safeViewport, Math.ceil(80 + bars.length * slot)));
    },

    isVisible: function (key) {
      var automaticStructureLayer = [
        "zigzag", "trendline", "ma", "support", "resistance"
      ].indexOf(key) >= 0;
      return this.data.visibility[key] === true || (
        this.data.autoIdentify === true && automaticStructureLayer
      );
    },

    eventIsVisible: function (item) {
      return this.data.eventVisibility[item.id] !== false;
    },

    resetLayerDrawAudit: function () {
      this.layerDrawAudit = {
        simple: 0,
        composite: 0,
        trend: 0,
        chart: 0,
        gap: 0,
        zigzag: 0,
        trendline: 0,
        ma: 0,
        support: 0,
        resistance: 0
      };
    },

    markLayerDraw: function (key) {
      if (!this.layerDrawAudit) {
        this.resetLayerDrawAudit();
      }
      if (Object.prototype.hasOwnProperty.call(this.layerDrawAudit, key)) {
        this.layerDrawAudit[key] += 1;
      }
    },

    getLayerDrawAudit: function () {
      if (!this.layerDrawAudit) {
        this.resetLayerDrawAudit();
      }
      return Object.assign({}, this.layerDrawAudit);
    },

    getLayoutAudit: function () {
      var period = normalizePeriod(this.data.period);
      return {
        canvasWidth: Number(this.data.canvasWidth || 0),
        viewportWidth: Number(this.data.viewportWidth || 0),
        scrollLeft: Number(this.data.scrollLeft || 0),
        renderedWidth: Number(this.canvasMetrics && this.canvasMetrics.width || 0),
        renderedHeight: Number(this.canvasMetrics && this.canvasMetrics.height || 0),
        barCount: Number(period && period.bars && period.bars.length || 0)
      };
    },

    resetLabelLayout: function () {
      this.labelBoxes = [];
      this.labelLayoutAudit = { attempted: 0, drawn: 0, skipped: 0, overlapCount: 0 };
    },

    getLabelLayoutAudit: function () {
      if (!this.labelLayoutAudit) this.resetLabelLayout();
      var boxes = (this.labelBoxes || []).map(function (box) {
          return Object.assign({}, box);
        });
      var overlapCount = 0;
      for (var leftIndex = 0; leftIndex < boxes.length; leftIndex += 1) {
        for (var rightIndex = leftIndex + 1; rightIndex < boxes.length; rightIndex += 1) {
          if (this.boxesIntersect(boxes[leftIndex], boxes[rightIndex])) overlapCount += 1;
        }
      }
      return Object.assign({}, this.labelLayoutAudit, {
        boxes: boxes,
        overlapCount: overlapCount
      });
    },

    boxesIntersect: function (left, right) {
      var gap = 3;
      return !(
        left.right + gap <= right.left ||
        right.right + gap <= left.left ||
        left.bottom + gap <= right.top ||
        right.bottom + gap <= left.top
      );
    },

    drawRoundedLabelBox: function (context, box, radius, background, borderColor, borderWidth) {
      var left = box.left;
      var top = box.top;
      var right = box.right;
      var bottom = box.bottom;
      var safeRadius = Math.max(0, Math.min(Number(radius || 0), (right - left) / 2, (bottom - top) / 2));
      context.beginPath();
      context.moveTo(left + safeRadius, top);
      context.lineTo(right - safeRadius, top);
      context.quadraticCurveTo(right, top, right, top + safeRadius);
      context.lineTo(right, bottom - safeRadius);
      context.quadraticCurveTo(right, bottom, right - safeRadius, bottom);
      context.lineTo(left + safeRadius, bottom);
      context.quadraticCurveTo(left, bottom, left, bottom - safeRadius);
      context.lineTo(left, top + safeRadius);
      context.quadraticCurveTo(left, top, left + safeRadius, top);
      context.closePath();
      context.fillStyle = background;
      context.fill();
      if (borderColor) {
        context.strokeStyle = borderColor;
        context.lineWidth = Number(borderWidth || 1);
        context.stroke();
      }
    },

    drawSafeLabel: function (context, value, x, y, options) {
      var text = String(value || "").trim();
      if (!text) return false;
      if (!this.labelLayoutAudit) this.resetLabelLayout();
      this.labelLayoutAudit.attempted += 1;
      options = options || {};
      var fontSize = Number(options.fontSize || 10);
      var align = options.align || "center";
      context.font = chartFont(fontSize, options.weight || "");
      var measured = null;
      try {
        measured = context.measureText && context.measureText(text);
      } catch (error) {
        measured = null;
      }
      var estimatedWidth = Array.from(text).reduce(function (total, character) {
        return total + (/^[\x00-\xff]$/.test(character) ? fontSize * 0.62 : fontSize);
      }, 0);
      var textWidth = measured && isFinite(measured.width) ? measured.width : estimatedWidth;
      var paddingX = Number(options.paddingX || 6);
      var boxWidth = Math.max(16, textWidth + paddingX * 2);
      var boxHeight = fontSize + Number(options.paddingY || 8);
      var minLeft = Number(options.left !== undefined ? options.left : 8);
      var maxRight = Number(options.right !== undefined ? options.right : this.canvasMetrics.width - 8);
      var minTop = Number(options.top !== undefined ? options.top : 8);
      var maxBottom = Number(options.bottom !== undefined ? options.bottom : this.canvasMetrics.height - 8);
      var desiredLeft = align === "left" ? x : align === "right" ? x - boxWidth : x - boxWidth / 2;
      var yOffsets = [0, -14, 14, -28, 28, -42, 42];
      var xOffsets = [0, -20, 20, -40, 40];
      var chosen = null;
      for (var yIndex = 0; yIndex < yOffsets.length && !chosen; yIndex += 1) {
        for (var xIndex = 0; xIndex < xOffsets.length && !chosen; xIndex += 1) {
          var left = Math.max(minLeft, Math.min(maxRight - boxWidth, desiredLeft + xOffsets[xIndex]));
          var top = Math.max(minTop, Math.min(maxBottom - boxHeight, y + yOffsets[yIndex] - fontSize - 2));
          var candidate = {
            left: left,
            top: top,
            right: left + boxWidth,
            bottom: top + boxHeight,
            text: text
          };
          var overlaps = (this.labelBoxes || []).some(function (existing) {
            return this.boxesIntersect(candidate, existing);
          }, this);
          if (!overlaps) chosen = candidate;
        }
      }
      if (!chosen) {
        this.labelLayoutAudit.skipped += 1;
        return false;
      }
      this.labelBoxes.push(chosen);
      this.labelLayoutAudit.drawn += 1;
      context.save();
      this.drawRoundedLabelBox(
        context,
        chosen,
        Number(options.radius || 4),
        options.background || "rgba(255,255,255,0.94)",
        options.borderColor || "rgba(98,102,111,0.22)",
        options.borderWidth || 0.8
      );
      context.fillStyle = options.color || "#343741";
      context.font = chartFont(fontSize, options.weight || "");
      context.textBaseline = "alphabetic";
      context.textAlign = align;
      var drawX = align === "left"
          ? chosen.left + paddingX
          : align === "right"
          ? chosen.right - paddingX
          : (chosen.left + chosen.right) / 2;
      context.fillText(text, drawX, chosen.top + fontSize + 2);
      context.restore();
      return true;
    },

    draw: function () {
      var component = this;
      var query = wx.createSelectorQuery().in(this);
      query.select("#chartViewport").boundingClientRect();
      query.select("#klineCanvas").fields({ node: true, size: true });
      query.exec(function (result) {
        if (!result || !result[0] || !result[1] || !result[1].node) {
          return;
        }
        var viewportWidth = Number(result[0].width) || component.data.viewportWidth || 320;
        var period = normalizePeriod(component.data.period);
        var desiredWidth = component.calculateCanvasWidth(viewportWidth, period);
        var signature = component.getPeriodSignature(period);
        var widthChanged = Math.abs(Number(component.data.canvasWidth) - desiredWidth) > 1;
        var periodChanged = signature !== component.lastPeriodSignature;
        if (widthChanged || periodChanged) {
          component.lastPeriodSignature = signature;
          component.scrollAnchorTick = component.scrollAnchorTick ? 0 : 1;
          // The canvas keeps a right-side price-axis gutter.  Scrolling to the
          // mathematical maximum wastes that gutter and can clip a label at
          // the left edge, so stop one axis-width earlier.
          var latestScrollLeft = Math.max(
            0,
            desiredWidth - viewportWidth - LATEST_VIEWPORT_GUTTER - component.scrollAnchorTick
          );
          component.setData({
            canvasWidth: desiredWidth,
            viewportWidth: viewportWidth,
            scrollLeft: 0
          }, function () {
            var applyLatestPosition = function () {
              component.setData({ scrollLeft: latestScrollLeft }, function () {
                component.scheduleDraw();
              });
            };
            if (wx.nextTick) {
              wx.nextTick(applyLatestPosition);
            } else {
              clearTimeout(component.scrollTimer);
              component.scrollTimer = setTimeout(applyLatestPosition, 20);
            }
          });
          return;
        }
        var canvas = result[1].node;
        var width = result[1].width;
        var height = result[1].height;
        var ratio = wx.getWindowInfo ? wx.getWindowInfo().pixelRatio : wx.getSystemInfoSync().pixelRatio;
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        var context = canvas.getContext("2d");
        context.scale(ratio, ratio);
        component.canvasMetrics = { width: width, height: height };
        component.renderCanvas(context, width, height);
      });
    },

    renderCanvas: function (context, width, height) {
      this.resetLayerDrawAudit();
      var period = normalizePeriod(this.data.period);
      if (!period || !period.bars || !period.bars.length) {
        context.clearRect(0, 0, width, height);
        return;
      }
      var bars = period.bars;
      var pad = { left: 16, right: 64, top: 34, bottom: 32 };
      var chartWidth = width - pad.left - pad.right;
      var chartHeight = height - pad.top - pad.bottom;
      var values = [];
      bars.forEach(function (bar) {
        if (period.displayMode === "trend" && bar.smooth !== null && bar.smooth !== undefined) {
          values.push(bar.smooth);
        } else {
          values.push(bar.high, bar.low);
        }
        if (bar.ma !== null && bar.ma !== undefined) {
          values.push(bar.ma);
        }
      });
      values.push(period.support, period.resistance);
      values = values.filter(function (value) {
        return typeof value === "number" && isFinite(value);
      });
      if (!values.length) {
        context.clearRect(0, 0, width, height);
        return;
      }
      var min = Math.min.apply(null, values);
      var max = Math.max.apply(null, values);
      var span = Math.max(max - min, Math.abs(max) * 0.02, 0.01);
      min -= span * 0.06;
      max += span * 0.06;
      span = max - min;
      var xAt = function (index) {
        return pad.left + ((index + 0.5) / bars.length) * chartWidth;
      };
      var yAt = function (price) {
        return pad.top + ((max - price) / span) * chartHeight;
      };
      this.chartScale = { bars: bars, pad: pad, chartWidth: chartWidth, xAt: xAt };

      context.clearRect(0, 0, width, height);
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, width, height);
      this.resetLabelLayout();
      this.drawGrid(context, width, height, pad, min, max, yAt);
      this.drawLevels(context, period, pad, chartWidth, yAt);
      if (period.displayMode === "trend") {
        this.drawSmoothTrend(context, bars, xAt, yAt);
      } else {
        this.drawCandles(context, bars, chartWidth, xAt, yAt);
      }
      this.drawMovingAverage(context, bars, xAt, yAt);
      this.drawGraphics(context, period.graphics || [], xAt, yAt);
      this.drawPatterns(context, period.patterns || [], bars, xAt, yAt, pad);
      this.drawDates(context, bars, width, height, pad);
    },

    drawGrid: function (context, width, height, pad, min, max, yAt) {
      context.font = chartFont(10);
      context.textAlign = "left";
      context.textBaseline = "middle";
      for (var index = 0; index <= 4; index += 1) {
        var price = min + ((max - min) * index) / 4;
        var y = yAt(price);
        context.strokeStyle = "#edf0f4";
        context.lineWidth = 1;
        context.setLineDash([3, 4]);
        context.beginPath();
        context.moveTo(pad.left, y);
        context.lineTo(width - pad.right, y);
        context.stroke();
        context.setLineDash([]);
        context.fillStyle = "#62666f";
        context.fillText(price.toFixed(2), width - pad.right + 5, y);
      }
      for (var vertical = 1; vertical < 4; vertical += 1) {
        var chartWidth = width - pad.left - pad.right;
        var x = pad.left + (chartWidth * vertical) / 4;
        context.strokeStyle = "#f4f6f8";
        context.setLineDash([2, 4]);
        context.beginPath();
        context.moveTo(x, pad.top);
        context.lineTo(x, height - pad.bottom);
        context.stroke();
        context.setLineDash([]);
      }
    },

    drawCandles: function (context, bars, chartWidth, xAt, yAt) {
      var bodyWidth = Math.max(2, Math.min(8, (chartWidth / bars.length) * 0.58));
      bars.forEach(function (bar, index) {
        var up = bar.close >= bar.open;
        var color = up ? "#ef5350" : "#26a69a";
        var x = xAt(index);
        var highY = yAt(bar.high);
        var lowY = yAt(bar.low);
        var openY = yAt(bar.open);
        var closeY = yAt(bar.close);
        var bodyTop = Math.min(openY, closeY);
        var bodyHeight = Math.max(1.4, Math.abs(closeY - openY));
        context.strokeStyle = color;
        context.fillStyle = color;
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(x, highY);
        context.lineTo(x, lowY);
        context.stroke();
        context.fillRect(x - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight);
      });
    },

    drawSmoothTrend: function (context, bars, xAt, yAt) {
      var started = false;
      context.strokeStyle = "#2962ff";
      context.lineWidth = 3;
      context.lineJoin = "round";
      context.lineCap = "round";
      context.beginPath();
      bars.forEach(function (bar, index) {
        var value = bar.smooth !== undefined && bar.smooth !== null ? bar.smooth : bar.close;
        if (value === undefined || value === null || !isFinite(value)) return;
        var x = xAt(index);
        var y = yAt(value);
        if (!started) { context.moveTo(x, y); started = true; } else context.lineTo(x, y);
      });
      if (started) context.stroke();
      context.fillStyle = "#2962ff";
      var last = bars[bars.length - 1];
      var lastValue = last && (last.smooth !== undefined && last.smooth !== null ? last.smooth : last.close);
      if (lastValue !== undefined && lastValue !== null) {
        this.drawSafeLabel(
          context,
          "平滑趋势 " + Number(lastValue).toFixed(2),
          this.canvasMetrics.width - 8,
          Math.max(14, yAt(lastValue) - 8),
          { align: "right", color: "#2962ff", right: this.canvasMetrics.width - 5 }
        );
      }
    },

    drawMovingAverage: function (context, bars, xAt, yAt) {
      if (!this.isVisible("ma")) {
        return;
      }
      context.strokeStyle = "rgba(245,166,35,0.88)";
      context.lineWidth = 1.45;
      context.beginPath();
      var started = false;
      bars.forEach(function (bar, index) {
        if (bar.ma === null || bar.ma === undefined) {
          return;
        }
        var x = xAt(index);
        var y = yAt(bar.ma);
        if (!started) {
          context.moveTo(x, y);
          started = true;
        } else {
          context.lineTo(x, y);
        }
      });
      if (started) {
        context.stroke();
        this.markLayerDraw("ma");
      }
    },

    drawLevels: function (context, period, pad, chartWidth, yAt) {
      var component = this;
      [
        { key: "support", price: period.support, color: "#26a69a", label: "支撑" },
        { key: "resistance", price: period.resistance, color: "#ef5350", label: "阻力" }
      ].forEach(function (level) {
        var graphic = (period.graphics || []).find(function (item) {
          return item.type === level.key;
        });
        if (
          !component.isVisible(level.key) ||
          (graphic && !component.eventIsVisible(graphic)) ||
          typeof level.price !== "number" ||
          !isFinite(level.price)
        ) {
          return;
        }
        var y = yAt(level.price);
        context.strokeStyle = level.color;
        context.fillStyle = level.color;
        context.globalAlpha = 0.72;
        context.lineWidth = 1;
        context.setLineDash([4, 5]);
        context.beginPath();
        context.moveTo(pad.left, y);
        context.lineTo(pad.left + chartWidth, y);
        context.stroke();
        context.setLineDash([]);
        context.globalAlpha = 1;
        component.drawSafeLabel(
          context,
          level.label + " " + Number(level.price).toFixed(2),
          pad.left + 4,
          y - 8,
          {
            align: "left",
            fontSize: 11,
            color: level.color,
            left: pad.left,
            right: pad.left + chartWidth,
            top: pad.top,
            bottom: component.canvasMetrics.height - pad.bottom
          }
        );
        component.markLayerDraw(level.key);
      });
    },

    drawGraphics: function (context, graphics, xAt, yAt) {
      var component = this;
      graphics.forEach(function (graphic) {
        if (!component.eventIsVisible(graphic)) {
          return;
        }
        if (graphic.type === "zigzag" && component.isVisible("zigzag")) {
          if (component.drawPolyline(context, graphic.points, xAt, yAt, "rgba(105,115,130,0.40)", 1.05, [], false)) {
            component.markLayerDraw("zigzag");
          }
        }
        if (graphic.type === "trendline" && component.isVisible("trendline")) {
          if (component.drawPolyline(
            context,
            graphic.points,
            xAt,
            yAt,
            "rgba(126,87,194,0.90)",
            1.55,
            [7, 5],
            true
          )) {
            component.markLayerDraw("trendline");
          }
        }
      });
    },

    drawPolyline: function (context, points, xAt, yAt, color, width, dash, straight) {
      var period = normalizePeriod(this.data.period);
      var barCount = period && period.bars ? period.bars.length : 0;
      points = asArray(points).map(function (point) {
        return {
          index: Number(point && point.index),
          price: Number(point && point.price),
          kind: point && point.kind
        };
      }).filter(function (point) {
        return isFinite(point.index) && isFinite(point.price) && (
          !barCount || (point.index >= 0 && point.index < barCount)
        );
      }).sort(function (left, right) {
        return left.index - right.index;
      }).filter(function (point, index, values) {
        return index === 0 || point.index !== values[index - 1].index;
      });
      if (straight && points.length > 2) {
        points = [points[0], points[points.length - 1]];
      }
      if (points.length < 2 || points[0].index === points[points.length - 1].index) {
        return false;
      }
      context.strokeStyle = color;
      context.lineWidth = width;
      context.setLineDash(dash || []);
      context.beginPath();
      points.forEach(function (point, index) {
        var x = xAt(point.index);
        var y = yAt(point.price);
        if (index === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      });
      context.stroke();
      context.setLineDash([]);
      return true;
    },

    drawPatterns: function (context, patterns, bars, xAt, yAt, pad) {
      var component = this;
      var selection = patternDisplay.selectForCanvas(patterns, {
        visibility: this.data.visibility,
        autoIdentify: this.data.autoIdentify,
        eventVisibility: this.data.eventVisibility
      });
      patterns = selection.drawn;
      var gapItems = patterns.filter(function (item) {
        return item.category === "gap" && component.eventIsVisible(item);
      });
      var gapIds = {};
      gapItems.forEach(function (item) { gapIds[item.id] = true; });
      var gapIndex = 0;
      var labelCount = 0;
      var maxLabels = 10;
      patterns.forEach(function (item, patternIndex) {
        if (!component.eventIsVisible(item)) {
          return;
        }
        if (item.category === "gap" && !gapIds[item.id]) {
          return;
        }
        var start = Math.max(0, Math.min(bars.length - 1, item.start));
        var end = Math.max(start, Math.min(bars.length - 1, item.end));
        var slice = bars.slice(start, end + 1);
        var topPrice = Math.max.apply(null, slice.map(function (bar) { return bar.high; }));
        var lowPrice = Math.min.apply(null, slice.map(function (bar) { return bar.low; }));
        var left = xAt(start) - 5;
        var right = xAt(end) + 5;
        var top = Math.max(pad.top + 6, yAt(topPrice) - 12 - (patternIndex % 2) * 12);
        var bottom = yAt(lowPrice) + 8;
        var color = item.direction === "bull" ? "#ef5350" : item.direction === "bear" ? "#26a69a" : "#62666f";
        context.strokeStyle = color;
        context.fillStyle = color;
        context.lineWidth = 1.3;
        if (item.category === "chart") {
          if (component.drawChartStructure(context, item, bars, start, end, xAt, yAt, pad)) {
            component.markLayerDraw("chart");
          }
          return;
        } else if (item.category === "simple") {
          context.beginPath();
          context.ellipse((left + right) / 2, (top + bottom) / 2, Math.max(7, (right - left) / 2), Math.max(13, (bottom - top) / 2), 0, 0, Math.PI * 2);
          context.stroke();
          component.markLayerDraw("simple");
        } else if (item.category === "composite") {
          context.strokeRect(left, top, Math.max(8, right - left), Math.max(18, bottom - top));
          component.markLayerDraw("composite");
        } else if (item.category === "trend") {
          context.setLineDash([5, 3]);
          context.beginPath();
          context.moveTo(left, bottom);
          context.lineTo(right, top);
          context.stroke();
          context.setLineDash([]);
          component.markLayerDraw("trend");
        } else if (item.category === "gap") {
          if (component.drawGap(context, item, bars, start, end, xAt, yAt, pad, gapIndex)) {
            component.markLayerDraw("gap");
          }
          gapIndex += 1;
          return;
        } else {
          context.setLineDash([3, 3]);
          context.strokeRect(left, top, Math.max(8, right - left), Math.max(18, bottom - top));
          context.setLineDash([]);
          component.markLayerDraw("simple");
        }
        if (labelCount < maxLabels) {
          var label = item.name || item.displayName;
          if (component.drawSafeLabel(
            context,
            label,
            Math.max(pad.left + 22, (left + right) / 2),
            Math.max(pad.top + 12, top - 5),
            {
              fontSize: 10,
              color: color,
              borderColor: color,
              left: pad.left,
              right: component.canvasMetrics.width - pad.right,
              top: pad.top,
              bottom: component.canvasMetrics.height - pad.bottom
            }
          )) labelCount += 1;
        }
      });
    },

    drawGap: function (context, item, bars, start, end, xAt, yAt, pad, gapIndex) {
      var previous = bars[Math.max(0, start - 1)];
      var current = bars[Math.min(bars.length - 1, start)];
      if (!previous || !current) {
        return false;
      }
      var upper = item.direction === "bear" ? previous.low : current.low;
      var lower = item.direction === "bear" ? current.high : previous.high;
      if (upper < lower) {
        var swap = upper;
        upper = lower;
        lower = swap;
      }
      var left = Math.max(pad.left, xAt(start) - 8);
      var right = Math.min(this.canvasMetrics.width - pad.right, xAt(end) + 8);
      var validGap = item.direction === "bear"
        ? current.high < previous.low
        : current.low > previous.high;
      if (!validGap) {
        return false;
      }
      var color = item.direction === "bear" ? "#26a69a" : "#ef5350";
      [upper, lower].forEach(function (price) {
        var y = yAt(price);
        context.strokeStyle = color;
        context.lineWidth = 1.1;
        context.setLineDash([5, 4]);
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(right, y);
        context.stroke();
        context.setLineDash([]);
      });
      var label = (item.direction === "bear" ? "下降缺口" : "上升缺口") + (item.filled ? "·已补" : "·未补");
      var labelY = Math.max(pad.top + 12, yAt(upper) - 5 - gapIndex * 12);
      this.drawSafeLabel(context, label, (left + right) / 2, labelY, {
        fontSize: 10,
        color: color,
        borderColor: color,
        left: pad.left,
        right: this.canvasMetrics.width - pad.right,
        top: pad.top,
        bottom: this.canvasMetrics.height - pad.bottom
      });
      return true;
    },

    drawExactGeometry: function (context, item, xAt, yAt, pad) {
      var geometry = item.geometry || {};
      var lines = asArray(geometry.lines);
      var arcs = asArray(geometry.arcs);
      var pivots = asArray(geometry.pivots).map(asArray);
      if (!lines.length && !arcs.length && !pivots.length) {
        return false;
      }
      var color = item.direction === "bull" ? "#ef5350" : item.direction === "bear" ? "#26a69a" : "#2962ff";
      var roleLabels = {
        neckline: "颈线",
        resistance: "阻力",
        support: "支撑",
        base_resistance: "箱体上沿",
        base_support: "箱体下沿",
        rim_resistance: "杯沿",
        handle_support: "柄支撑"
      };
      var component = this;
      var labelPivot = pivots.length ? pivots.reduce(function (best, pivot) {
        return Number(pivot[1]) > Number(best[1]) ? pivot : best;
      }, pivots[0]) : null;
      var labelX = labelPivot ? xAt(Number(labelPivot[0])) : xAt(Number(item.end || item.start || 0));
      var labelY = labelPivot ? yAt(Number(labelPivot[1])) : pad.top + 12;
      // Reserve the clearest label position for the canonical pattern name.
      // Supporting labels are placed afterwards and yield on collision.
      this.drawSafeLabel(context, item.name || item.displayName || "技术图形", labelX, Math.max(pad.top + 10, labelY - 12), {
        fontSize: 12,
        weight: "700",
        color: "#2962ff",
        borderColor: "#2962ff",
        background: "rgba(245,248,255,0.97)",
        left: pad.left,
        right: this.canvasMetrics.width - pad.right,
        top: pad.top,
        bottom: this.canvasMetrics.height - pad.bottom
      });
      lines.forEach(function (line) {
        var x1 = Number(line.x1);
        var x2 = Number(line.x2);
        var y1 = Number(line.y1);
        var y2 = Number(line.y2);
        if (![x1, x2, y1, y2].every(isFinite)) {
          return;
        }
        component.drawPatternLine(
          context,
          x1,
          y1,
          x2,
          y2,
          xAt,
          yAt,
          color,
          roleLabels[line.role] || ""
        );
      });
      arcs.forEach(function (arc) {
        var coefficients = arc.coefficients || [];
        if (coefficients.length !== 3) {
          return;
        }
        var start = Number(arc.start);
        var end = Number(arc.end);
        var a = Number(coefficients[0]);
        var b = Number(coefficients[1]);
        var c = Number(coefficients[2]);
        if (![start, end, a, b, c].every(isFinite) || end <= start) {
          return;
        }
        context.strokeStyle = color;
        context.lineWidth = 1.6;
        context.setLineDash([]);
        context.beginPath();
        for (var step = 0; step <= 36; step += 1) {
          var xValue = start + ((end - start) * step) / 36;
          var yValue = a * xValue * xValue + b * xValue + c;
          if (step === 0) {
            context.moveTo(xAt(xValue), yAt(yValue));
          } else {
            context.lineTo(xAt(xValue), yAt(yValue));
          }
        }
        context.stroke();
      });
      var pivotLabels = {
        left_shoulder: "左肩",
        head: "头",
        right_shoulder: "右肩"
      };
      pivots.forEach(function (pivot) {
        if (!Array.isArray(pivot) || pivot.length < 2) {
          return;
        }
        var index = Number(pivot[0]);
        var price = Number(pivot[1]);
        if (!isFinite(index) || !isFinite(price)) {
          return;
        }
        var x = xAt(index);
        var y = yAt(price);
        context.fillStyle = color;
        context.beginPath();
        context.arc(x, y, 2.8, 0, Math.PI * 2);
        context.fill();
        var label = pivotLabels[pivot[2]];
        if (label) {
          component.drawSafeLabel(context, label, x, Math.max(pad.top + 10, y - 7), {
            fontSize: 10,
            color: color,
            left: pad.left,
            right: component.canvasMetrics.width - pad.right,
            top: pad.top,
            bottom: component.canvasMetrics.height - pad.bottom
          });
        }
      });
      return true;
    },

    drawChartStructure: function (context, item, bars, start, end, xAt, yAt, pad) {
      // FAE geometry is authoritative.  Reconstructing a neckline from the
      // whole visible range used to create unexplained long diagonals and
      // oversized island boxes even when the backend supplied local pivots.
      if (this.drawExactGeometry(context, item, xAt, yAt, pad)) {
        return true;
      }
      var name = item.name || "技术图形";
      var slice = bars.slice(start, end + 1);
      if (!slice.length) {
        return false;
      }
      var blue = "#2962ff";
      var highValues = slice.map(function (bar) { return bar.high; });
      var lowValues = slice.map(function (bar) { return bar.low; });
      var maxHigh = Math.max.apply(null, highValues);
      var minLow = Math.min.apply(null, lowValues);

      // Legacy payloads may carry a chart-pattern name without exact pivots.
      // In that case only mark the local span: never invent a diagonal from
      // the full visible range, because it looks authoritative but is not.
      var left = Math.max(pad.left, xAt(start) - 5);
      var right = Math.min(this.canvasMetrics.width - pad.right, xAt(end) + 5);
      var top = Math.max(pad.top + 4, yAt(maxHigh) - 7);
      var bottom = Math.min(this.canvasMetrics.height - pad.bottom, yAt(minLow) + 7);
      context.strokeStyle = "rgba(41,98,255,0.48)";
      context.lineWidth = 1.1;
      context.setLineDash([4, 4]);
      context.strokeRect(left, top, Math.max(10, right - left), Math.max(18, bottom - top));
      context.setLineDash([]);

      this.drawSafeLabel(
        context,
        item.name || item.displayName || name,
        Math.max(pad.left + 28, (xAt(start) + xAt(end)) / 2),
        Math.max(pad.top + 10, yAt(maxHigh) - 8),
        {
          fontSize: 11,
          weight: "700",
          color: blue,
          borderColor: blue,
          background: "rgba(245,248,255,0.97)",
          left: pad.left,
          right: this.canvasMetrics.width - pad.right,
          top: pad.top,
          bottom: this.canvasMetrics.height - pad.bottom
        }
      );
      return true;
    },

    drawPatternLine: function (context, start, startPrice, end, endPrice, xAt, yAt, color, label) {
      var x1 = xAt(start);
      var x2 = xAt(end);
      var y1 = yAt(startPrice);
      var y2 = yAt(endPrice);
      context.strokeStyle = color;
      context.fillStyle = color;
      context.lineWidth = 1.5;
      context.setLineDash([6, 4]);
      context.beginPath();
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
      context.stroke();
      context.setLineDash([]);
      this.drawSafeLabel(context, label, x2 - 2, Math.max(12, Math.min(y2 - 5, this.canvasMetrics.height - 8)), {
        align: "right",
        fontSize: 10,
        color: color,
        borderColor: color,
        left: 8,
        right: this.canvasMetrics.width - 8,
        top: 8,
        bottom: this.canvasMetrics.height - 8
      });
    },

    drawDates: function (context, bars, width, height, pad) {
      context.fillStyle = "#62666f";
      context.font = chartFont(10);
      context.textBaseline = "bottom";
      context.textAlign = "left";
      var firstDate = bars[0] && bars[0].date ? String(bars[0].date).slice(0, 10) : "";
      var lastDate = bars[bars.length - 1] && bars[bars.length - 1].date
        ? String(bars[bars.length - 1].date).slice(0, 10)
        : "";
      context.fillText(firstDate, pad.left, height - 7);
      context.textAlign = "right";
      context.fillText(lastDate, width - pad.right, height - 7);
      context.textAlign = "left";
      context.textBaseline = "alphabetic";
    },

    handleTap: function (event) {
      if (!this.chartScale) {
        return;
      }
      var touch = event.changedTouches && event.changedTouches[0];
      var x = event.detail && event.detail.x !== undefined
        ? event.detail.x
        : touch
          ? touch.x
          : 0;
      var scale = this.chartScale;
      var relative = (x - scale.pad.left) / scale.chartWidth;
      var index = Math.round(relative * scale.bars.length - 0.5);
      index = Math.max(0, Math.min(scale.bars.length - 1, index));
      this.setData({ selectedBar: scale.bars[index] });
      this.triggerEvent("barselect", { bar: scale.bars[index], index: index });
    }
  }
});
