Component({
  properties: {
    type: {
      type: String,
      value: "candle",
      observer: "scheduleDraw"
    },
    direction: {
      type: String,
      value: "neutral",
      observer: "scheduleDraw"
    }
  },

  lifetimes: {
    ready: function () {
      this.scheduleDraw();
    },
    detached: function () {
      clearTimeout(this.drawTimer);
    }
  },

  methods: {
    scheduleDraw: function () {
      var component = this;
      clearTimeout(this.drawTimer);
      this.drawTimer = setTimeout(function () {
        component.draw();
      }, 30);
    },

    draw: function () {
      var component = this;
      wx.createSelectorQuery().in(this).select("#sketchCanvas")
        .fields({ node: true, size: true })
        .exec(function (result) {
          if (!result || !result[0] || !result[0].node) {
            return;
          }
          var canvas = result[0].node;
          var width = result[0].width;
          var height = result[0].height;
          var info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
          var ratio = info.pixelRatio || 1;
          canvas.width = width * ratio;
          canvas.height = height * ratio;
          var context = canvas.getContext("2d");
          context.scale(ratio, ratio);
          component.render(context, width, height);
        });
    },

    line: function (context, points, color, width, dash) {
      context.strokeStyle = color || "#2962ff";
      context.lineWidth = width || 1.5;
      context.setLineDash(dash || []);
      context.beginPath();
      points.forEach(function (point, index) {
        if (index === 0) {
          context.moveTo(point[0], point[1]);
        } else {
          context.lineTo(point[0], point[1]);
        }
      });
      context.stroke();
      context.setLineDash([]);
    },

    label: function (context, text, x, y, color) {
      context.fillStyle = color || "#787b86";
      context.font = '10px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif';
      context.fillText(text, x, y);
    },

    render: function (context, width, height) {
      var type = this.data.type;
      var blue = "#2962ff";
      var red = "#df5a62";
      var green = "#4fa58e";
      var grid = "#e8edf2";
      context.clearRect(0, 0, width, height);
      context.lineCap = "round";
      context.lineJoin = "round";
      context.fillStyle = "#edf7f8";
      context.fillRect(0, 0, width, height);
      if (type.indexOf("pattern:") === 0 || type.indexOf("candle") >= 0) {
        context.strokeStyle = "#e4eef1";
        context.lineWidth = 0.8;
        for (var i = 1; i < 4; i += 1) {
          context.beginPath();
          context.moveTo(0, (height * i) / 4);
          context.lineTo(width, (height * i) / 4);
          context.stroke();
        }
      }
      if (type.indexOf("pattern:") === 0) {
        this.drawCandlestickPattern(context, width, height, type.slice(8), red, green, blue);
        return;
      }
      if (type.indexOf("candle") >= 0 || ["body", "upper_shadow", "lower_shadow", "high_low"].indexOf(type) >= 0) {
        this.drawCandle(context, width, height, type, red, green);
        return;
      }
      if (type === "support" || type === "resistance" || type === "neckline" || type === "gap" || type === "volume") {
        this.drawBasicLine(context, width, height, type, red, green, blue);
        return;
      }
      this.drawChartPattern(context, width, height, type, red, green, blue, grid);
    },

    drawCandlestickPattern: function (context, width, height, name, red, green, blue) {
      var aliases = {
        "锤头线": "锤子线",
        "身怀六甲": "看涨孕线",
        "弹友反攻": "淡友反攻",
        "高开逃逸": "高开出逃",
        "低开突涨": "下探上涨",
        "三个白色武士": "红三兵"
      };
      name = aliases[name] || name;
      var candles = this.patternCandles(name);
      var values = [];
      candles.forEach(function (bar) {
        values.push(bar.h, bar.l);
      });
      var min = Math.min.apply(null, values);
      var max = Math.max.apply(null, values);
      var span = Math.max(1, max - min);
      var top = 14;
      var bottom = height - 14;
      var yAt = function (price) {
        return bottom - ((price - min) / span) * (bottom - top);
      };
      var slot = (width - 24) / candles.length;
      var bodyWidth = Math.max(5, Math.min(14, slot * 0.44));
      candles.forEach(function (bar, index) {
        var x = 12 + slot * (index + 0.5);
        var color = bar.c >= bar.o ? red : green;
        var openY = yAt(bar.o);
        var closeY = yAt(bar.c);
        var bodyTop = Math.min(openY, closeY);
        var bodyHeight = Math.max(2, Math.abs(closeY - openY));
        context.strokeStyle = color;
        context.fillStyle = color;
        context.lineWidth = 1.2;
        context.beginPath();
        context.moveTo(x, yAt(bar.h));
        context.lineTo(x, yAt(bar.l));
        context.stroke();
        context.fillRect(x - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight);
      });
      this.drawCandleGuides(context, name, candles, yAt, slot, width, height, blue, red, green);
    },

    patternCandles: function (name) {
      var b = function (open, close, high, low) {
        return { o: open, c: close, h: high, l: low };
      };
      var rise = [b(24, 38, 42, 20), b(36, 52, 57, 33), b(50, 68, 72, 47)];
      var fall = [b(76, 62, 80, 58), b(64, 48, 68, 44), b(50, 34, 54, 30)];
      var map = {
        "十字星": [b(48, 49, 70, 28)],
        "长十字星": [b(49, 50, 92, 8)],
        "螺旋桨": [b(45, 53, 82, 17)],
        "射击之星": rise.concat([b(72, 67, 96, 64)]),
        "锤子线": fall.concat([b(28, 36, 40, 4)]),
        "倒锤头线": fall.concat([b(28, 35, 61, 24)]),
        "吊颈线": rise.concat([b(72, 67, 76, 40)]),
        "T字线": [b(74, 75, 78, 14)],
        "倒T字线": [b(25, 24, 86, 21)],
        "一字线": [b(50, 50, 50, 50)],
        "曙光初现": fall.concat([b(55, 24, 59, 20), b(18, 43, 47, 15)]),
        "乌云盖顶": rise.concat([b(40, 74, 78, 36), b(84, 55, 87, 51)]),
        "看涨吞没": fall.concat([b(44, 30, 48, 27), b(24, 54, 58, 21)]),
        "看跌吞没": rise.concat([b(50, 68, 72, 47), b(76, 42, 79, 39)]),
        "看涨孕线": fall.concat([b(44, 19, 47, 16), b(25, 34, 37, 22)]),
        "看跌孕线": rise.concat([b(51, 78, 81, 48), b(71, 61, 74, 58)]),
        "好友反攻": fall.concat([b(58, 28, 61, 24), b(18, 28, 32, 15)]),
        "淡友反攻": rise.concat([b(42, 72, 76, 38), b(82, 72, 85, 68)]),
        "旭日东升": fall.concat([b(68, 34, 72, 30), b(46, 84, 88, 42)]),
        "倾盆大雨": rise.concat([b(34, 68, 72, 30), b(56, 18, 60, 14)]),
        "高开出逃": [b(28, 42, 46, 25), b(40, 55, 60, 37), b(53, 64, 68, 50), b(92, 20, 92, 16)],
        "下探上涨": [b(72, 58, 76, 55), b(60, 45, 64, 42), b(47, 35, 50, 31), b(8, 82, 86, 8)],
        "平顶": rise.concat([b(58, 76, 83, 55), b(74, 61, 83, 58)]),
        "平底": fall.concat([b(44, 27, 47, 18), b(28, 43, 47, 18)]),
        "搓揉线": rise.concat([b(70, 65, 92, 48), b(64, 69, 87, 45)]),
        "尽头线": rise.concat([b(58, 76, 96, 55), b(86, 89, 92, 83)]),
        "早晨之星": fall.concat([b(43, 18, 46, 15), b(14, 17, 23, 9), b(20, 49, 53, 18)]),
        "黄昏之星": rise.concat([b(52, 80, 84, 49), b(84, 81, 90, 76), b(78, 48, 81, 45)]),
        "早晨十字星": fall.concat([b(43, 18, 46, 15), b(13, 13, 20, 7), b(18, 50, 54, 16)]),
        "黄昏十字星": rise.concat([b(52, 80, 84, 49), b(86, 86, 92, 79), b(80, 47, 83, 44)]),
        "红三兵": [b(22, 40, 43, 19), b(35, 55, 59, 32), b(51, 72, 76, 48)],
        "三只乌鸦": [b(82, 61, 85, 58), b(66, 43, 69, 40), b(48, 24, 51, 21)],
        "黑三兵": [b(78, 59, 81, 56), b(61, 43, 64, 40), b(45, 27, 48, 24)],
        "下跌三连阴": [b(79, 63, 82, 60), b(61, 45, 65, 42), b(43, 26, 47, 22)],
        "上升三法": [b(20, 62, 66, 17), b(57, 49, 60, 45), b(51, 43, 54, 39), b(45, 52, 55, 41), b(50, 82, 86, 48)],
        "下降三法": [b(82, 40, 85, 37), b(45, 53, 57, 42), b(51, 59, 63, 48), b(57, 50, 61, 47), b(52, 20, 55, 17)],
        "高位并排阳线": rise.concat([b(78, 88, 91, 76), b(79, 90, 93, 77), b(80, 91, 94, 78)]),
        "低位并排阴线": fall.concat([b(22, 12, 24, 9), b(21, 11, 23, 8), b(20, 10, 22, 7)]),
        "两只乌鸦": rise.concat([b(85, 77, 88, 73), b(80, 62, 83, 58)]),
        "多方尖兵": [b(20, 52, 56, 18), b(49, 42, 52, 38), b(44, 48, 51, 41), b(46, 69, 73, 44)],
        "空方尖兵": [b(80, 48, 83, 44), b(51, 58, 61, 47), b(56, 52, 60, 49), b(54, 31, 57, 27)],
        "倒三阳": [b(78, 86, 89, 74), b(67, 75, 78, 63), b(56, 64, 67, 52)],
        "塔形顶": [b(24, 63, 67, 21), b(62, 69, 73, 58), b(68, 66, 72, 62), b(67, 61, 70, 57), b(60, 25, 63, 22)],
        "塔形底": [b(78, 39, 81, 36), b(40, 33, 44, 29), b(34, 36, 40, 30), b(35, 41, 45, 32), b(42, 77, 81, 39)],
        "岛形顶": [b(24, 38, 42, 21), b(36, 49, 53, 33), b(68, 82, 86, 65), b(79, 75, 85, 72), b(76, 84, 88, 73), b(58, 39, 61, 35), b(41, 29, 44, 26)],
        "岛形底": [b(78, 64, 81, 61), b(66, 52, 69, 49), b(34, 20, 37, 16), b(22, 27, 31, 18), b(26, 18, 29, 15), b(44, 66, 70, 41), b(65, 77, 81, 62)],
        "加速上升": [b(14, 21, 23, 12), b(20, 28, 31, 18), b(27, 38, 41, 25), b(37, 51, 54, 35), b(50, 69, 73, 48), b(68, 91, 95, 65)],
        "加速下跌": [b(90, 83, 93, 80), b(84, 75, 87, 72), b(76, 64, 79, 61), b(65, 50, 68, 47), b(51, 32, 54, 29), b(33, 9, 36, 6)],
        "冉冉上升": [b(20, 28, 31, 18), b(27, 34, 37, 25), b(33, 41, 44, 31), b(40, 48, 51, 38), b(47, 55, 58, 45), b(54, 63, 66, 52)],
        "绵绵阴跌": [b(78, 70, 81, 68), b(71, 65, 74, 62), b(66, 59, 69, 57), b(60, 54, 63, 51), b(55, 48, 58, 45), b(49, 41, 52, 38)],
        "徐缓上升": [b(22, 31, 34, 20), b(30, 36, 39, 27), b(35, 43, 46, 33), b(42, 49, 52, 39), b(48, 56, 59, 46), b(55, 63, 66, 53)],
        "徐缓下降": [b(76, 67, 79, 64), b(68, 62, 71, 59), b(63, 56, 66, 53), b(57, 50, 60, 47), b(51, 44, 54, 41), b(45, 37, 48, 34)],
        "稳步上涨": [b(20, 34, 37, 18), b(33, 30, 36, 27), b(31, 46, 49, 29), b(45, 41, 48, 38), b(42, 59, 62, 40), b(58, 72, 75, 55)],
        "稳步下跌": [b(80, 66, 83, 63), b(67, 70, 73, 64), b(69, 54, 72, 51), b(55, 59, 62, 52), b(58, 41, 61, 38), b(42, 28, 45, 25)],
        "升势受阻": [b(20, 42, 45, 18), b(40, 58, 62, 38), b(56, 68, 76, 53), b(66, 72, 84, 63), b(71, 73, 88, 68)],
        "跌势受阻": [b(82, 60, 85, 57), b(62, 45, 65, 41), b(47, 36, 50, 28), b(38, 32, 41, 20), b(34, 32, 37, 15)]
      };
      return map[name] || [b(25, 38, 42, 22), b(37, 31, 40, 28), b(32, 48, 52, 29)];
    },

    drawCandleGuides: function (context, name, candles, yAt, slot, width, height, blue, red, green) {
      var xAt = function (index) {
        return 12 + slot * (index + 0.5);
      };
      var last = candles.length - 1;
      var guide = function (price, start, end, label, color, labelBelow) {
        var y = yAt(price);
        this.line(context, [[xAt(start) - slot * 0.45, y], [xAt(end) + slot * 0.45, y]], color, 1.15, [4, 4]);
        this.label(context, label, Math.max(8, xAt(start) - slot * 0.42), y + (labelBelow ? 12 : -5), color);
      }.bind(this);
      if (name === "好友反攻" || name === "淡友反攻") {
        guide(candles[last].c, last - 1, last, "收盘近似", blue, false);
      } else if (name === "高开出逃") {
        guide(candles[last].o, 0, last, "高开基准", red, false);
      } else if (name === "下探上涨") {
        guide(candles[last].o, 0, last, "低开基准", green, true);
      } else if (name === "平顶") {
        guide(Math.min(candles[last - 1].h, candles[last].h), last - 1, last, "平顶", red, false);
      } else if (name === "平底") {
        guide(Math.max(candles[last - 1].l, candles[last].l), last - 1, last, "平底", green, true);
      } else if (name === "岛形顶") {
        guide(candles[1].h, 1, 4, "上跳缺口", blue, true);
        guide(candles[2].l, 1, 4, "", blue, false);
        guide(candles[5].h, 2, 5, "下跳缺口", blue, true);
        guide(candles[4].l, 2, 5, "", blue, false);
      } else if (name === "岛形底") {
        guide(candles[2].h, 1, 4, "下跳缺口", blue, true);
        guide(candles[1].l, 1, 4, "", blue, false);
        guide(candles[4].h, 2, 5, "", blue, false);
        guide(candles[5].l, 2, 5, "上跳缺口", blue, false);
      }
    },

    drawCandle: function (context, width, height, type, red, green) {
      var center = width * 0.5;
      var color = type === "bear_candle" ? green : red;
      var top = height * 0.16;
      var bottom = height * 0.84;
      var bodyTop = type === "lower_shadow" ? height * 0.24 : height * 0.34;
      var bodyBottom = type === "upper_shadow" ? height * 0.76 : height * 0.64;
      context.strokeStyle = color;
      context.fillStyle = color;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(center, top);
      context.lineTo(center, bottom);
      context.stroke();
      context.fillRect(center - 16, bodyTop, 32, bodyBottom - bodyTop);
      this.label(context, "最高", center + 22, top + 4);
      this.label(context, "最低", center + 22, bottom + 4);
      this.label(context, "上影线", center - 72, bodyTop - 18);
      this.label(context, "实体", center + 22, (bodyTop + bodyBottom) / 2);
      this.label(context, "下影线", center - 72, bodyBottom + 28);
    },

    drawBasicLine: function (context, width, height, type, red, green, blue) {
      if (type === "volume") {
        var bars = [0.35, 0.58, 0.42, 0.78, 0.62, 0.9, 0.54];
        bars.forEach(function (value, index) {
          context.fillStyle = index % 2 ? green : red;
          context.fillRect(18 + index * ((width - 36) / bars.length), height * (0.92 - value * 0.62), 10, value * height * 0.62);
        });
        this.label(context, "成交量用于确认价格运动", 18, 18);
        return;
      }
      var level = type === "resistance" ? height * 0.3 : type === "support" ? height * 0.72 : height * 0.55;
      var color = type === "resistance" || type === "neckline" ? red : green;
      this.line(context, [[12, level], [width - 12, level]], color, 1.5, [5, 4]);
      var prices = type === "gap"
        ? [[15, height * 0.7], [75, height * 0.62], [125, height * 0.34], [width - 15, height * 0.28]]
        : [[12, height * 0.48], [55, height * 0.32], [96, height * 0.62], [138, height * 0.42], [width - 12, height * 0.68]];
      this.line(context, prices, blue, 2, []);
      this.label(context, type === "neckline" ? "颈线" : type === "resistance" ? "阻力" : type === "support" ? "支撑" : "缺口区间", 16, level - 8, color);
    },

    drawChartPattern: function (context, width, height, type, red, green, blue) {
      var left = 16;
      var right = width * 0.76;
      var top = 18;
      var bottom = height - 18;
      var middle = height * 0.54;
      var dark = "#151b24";
      var path = [];
      var curved = false;
      var lineY = function (first, second, x) {
        if (second[0] === first[0]) {
          return first[1];
        }
        return first[1] + ((second[1] - first[1]) * (x - first[0])) / (second[0] - first[0]);
      };
      if (type === "double_top") {
        path = [[left, bottom], [width * 0.20, middle + 8], [width * 0.31, top + 16], [width * 0.43, middle], [width * 0.57, top + 18], [width * 0.68, middle], [width * 0.80, middle + 25]];
        this.keyLine(context, "颈线", middle, blue, right);
      } else if (type === "double_bottom") {
        path = [[left, top], [width * 0.20, middle - 8], [width * 0.31, bottom - 14], [width * 0.43, middle], [width * 0.57, bottom - 16], [width * 0.68, middle], [width * 0.80, middle - 25]];
        this.keyLine(context, "颈线", middle, blue, right);
      } else if (type === "triple_top" || type === "triple_bottom") {
        var isTop = type === "triple_top";
        path = isTop
          ? [[left, bottom], [width * 0.18, top + 18], [width * 0.30, middle], [width * 0.42, top + 16], [width * 0.54, middle], [width * 0.66, top + 19], [width * 0.73, middle], [width * 0.80, middle + 24]]
          : [[left, top], [width * 0.18, bottom - 18], [width * 0.30, middle], [width * 0.42, bottom - 16], [width * 0.54, middle], [width * 0.66, bottom - 19], [width * 0.73, middle], [width * 0.80, middle - 24]];
        this.keyLine(context, "颈线", middle, blue, right);
      } else if (type === "hs_top" || type === "hs_bottom") {
        var topShape = type === "hs_top";
        path = topShape
          ? [[left, bottom], [width * 0.20, top + 38], [width * 0.32, middle], [width * 0.46, top], [width * 0.58, middle], [width * 0.69, top + 38], [width * 0.75, middle], [width * 0.81, middle + 24]]
          : [[left, top], [width * 0.20, bottom - 38], [width * 0.32, middle], [width * 0.46, bottom], [width * 0.58, middle], [width * 0.69, bottom - 38], [width * 0.75, middle], [width * 0.81, middle - 24]];
        this.keyLine(context, "颈线", middle, blue, right);
      } else if (type === "ascending_triangle") {
        var ascResistanceY = top + 27;
        var ascSupport = [[left, bottom - 3], [right, ascResistanceY + 18]];
        var ascLow1X = width * 0.31;
        var ascLow2X = width * 0.50;
        var ascLow3X = width * 0.66;
        this.boundaries(context, [[left, ascResistanceY], [right, ascResistanceY]], ascSupport, right, red, green, blue);
        path = [
          [left, bottom - 3],
          [width * 0.21, ascResistanceY],
          [ascLow1X, lineY(ascSupport[0], ascSupport[1], ascLow1X)],
          [width * 0.41, ascResistanceY],
          [ascLow2X, lineY(ascSupport[0], ascSupport[1], ascLow2X)],
          [width * 0.59, ascResistanceY],
          [ascLow3X, lineY(ascSupport[0], ascSupport[1], ascLow3X)],
          [right, ascResistanceY],
          [width * 0.82, ascResistanceY - 18]
        ];
      } else if (type === "descending_triangle") {
        var descSupportY = bottom - 27;
        var descResistance = [[left, top + 3], [right, descSupportY - 18]];
        var descHigh1X = width * 0.31;
        var descHigh2X = width * 0.50;
        var descHigh3X = width * 0.66;
        this.boundaries(context, descResistance, [[left, descSupportY], [right, descSupportY]], right, red, green, blue);
        path = [
          [left, top + 3],
          [width * 0.21, descSupportY],
          [descHigh1X, lineY(descResistance[0], descResistance[1], descHigh1X)],
          [width * 0.41, descSupportY],
          [descHigh2X, lineY(descResistance[0], descResistance[1], descHigh2X)],
          [width * 0.59, descSupportY],
          [descHigh3X, lineY(descResistance[0], descResistance[1], descHigh3X)],
          [right, descSupportY],
          [width * 0.82, descSupportY + 18]
        ];
      } else if (type === "symmetrical_triangle") {
        this.boundaries(context, [[left, top], [right, middle]], [[left, bottom], [right, middle]], right, red, green, blue);
        path = [[left, top], [width * 0.24, bottom - 6], [width * 0.36, top + 24], [width * 0.48, bottom - 28], [width * 0.60, top + 43], [width * 0.69, bottom - 47], [right, middle]];
      } else if (type === "pennant") {
        var pennantStartX = width * 0.31;
        var pennantUpper = [[pennantStartX, top + 7], [right, middle]];
        var pennantLower = [[pennantStartX, top + 52], [right, middle]];
        this.boundaries(context, pennantUpper, pennantLower, right, red, green, blue);
        path = [
          [left, bottom],
          pennantUpper[0],
          [width * 0.40, lineY(pennantLower[0], pennantLower[1], width * 0.40)],
          [width * 0.49, lineY(pennantUpper[0], pennantUpper[1], width * 0.49)],
          [width * 0.57, lineY(pennantLower[0], pennantLower[1], width * 0.57)],
          [width * 0.65, lineY(pennantUpper[0], pennantUpper[1], width * 0.65)],
          [width * 0.71, lineY(pennantLower[0], pennantLower[1], width * 0.71)],
          [right, middle],
          [width * 0.82, middle - 30]
        ];
      } else if (type === "rectangle") {
        this.boundaries(context, [[left, top + 22], [right, top + 22]], [[left, bottom - 22], [right, bottom - 22]], right, red, green, blue);
        path = [[left, middle], [width * 0.20, top + 22], [width * 0.31, bottom - 22], [width * 0.43, top + 22], [width * 0.55, bottom - 22], [width * 0.67, top + 22], [right, middle]];
      } else if (type === "rising_wedge") {
        var riseUpper = [[left, bottom - 70], [right, top + 8]];
        var riseLower = [[left, bottom - 8], [right, top + 43]];
        this.boundaries(context, riseUpper, riseLower, right, red, green, blue);
        path = [
          riseLower[0],
          [width * 0.23, lineY(riseUpper[0], riseUpper[1], width * 0.23)],
          [width * 0.34, lineY(riseLower[0], riseLower[1], width * 0.34)],
          [width * 0.46, lineY(riseUpper[0], riseUpper[1], width * 0.46)],
          [width * 0.57, lineY(riseLower[0], riseLower[1], width * 0.57)],
          [width * 0.67, lineY(riseUpper[0], riseUpper[1], width * 0.67)],
          [width * 0.72, lineY(riseLower[0], riseLower[1], width * 0.72)],
          [width * 0.81, lineY(riseLower[0], riseLower[1], right) + 31]
        ];
      } else if (type === "falling_wedge") {
        var fallUpper = [[left, top + 8], [right, bottom - 44]];
        var fallLower = [[left, top + 70], [right, bottom - 8]];
        this.boundaries(context, fallUpper, fallLower, right, red, green, blue);
        path = [
          fallUpper[0],
          [width * 0.23, lineY(fallLower[0], fallLower[1], width * 0.23)],
          [width * 0.34, lineY(fallUpper[0], fallUpper[1], width * 0.34)],
          [width * 0.46, lineY(fallLower[0], fallLower[1], width * 0.46)],
          [width * 0.57, lineY(fallUpper[0], fallUpper[1], width * 0.57)],
          [width * 0.67, lineY(fallLower[0], fallLower[1], width * 0.67)],
          [width * 0.72, lineY(fallUpper[0], fallUpper[1], width * 0.72)],
          [width * 0.81, lineY(fallUpper[0], fallUpper[1], right) - 31]
        ];
      } else if (type === "flag") {
        var flagStartX = width * 0.31;
        var flagUpper = [[flagStartX, top + 7], [right, middle + 2]];
        var flagLower = [[flagStartX, top + 50], [right, middle + 45]];
        this.boundaries(context, flagUpper, flagLower, right, red, green, blue);
        path = [
          [left, bottom],
          flagUpper[0],
          [width * 0.41, lineY(flagLower[0], flagLower[1], width * 0.41)],
          [width * 0.50, lineY(flagUpper[0], flagUpper[1], width * 0.50)],
          [width * 0.59, lineY(flagLower[0], flagLower[1], width * 0.59)],
          [width * 0.68, lineY(flagUpper[0], flagUpper[1], width * 0.68)],
          [width * 0.73, lineY(flagLower[0], flagLower[1], width * 0.73)],
          [width * 0.82, middle - 25]
        ];
      } else if (type === "round_top" || type === "round_bottom") {
        for (var i = 0; i <= 12; i += 1) {
          var x = left + ((right - left) * i) / 12;
          var curve = Math.sin((Math.PI * i) / 12);
          var y = type === "round_top" ? bottom - curve * (bottom - top) : top + curve * (bottom - top);
          path.push([x, y]);
        }
        curved = true;
        this.keyLine(context, type === "round_top" ? "支撑" : "阻力", type === "round_top" ? bottom - 10 : top + 10, blue, right);
    } else if (type === "cup_with_handle" || type === "cup_handle") {
        var cupRim = top + 24;
        path = [[left, cupRim], [width * 0.20, middle + 12], [width * 0.31, bottom - 8], [width * 0.43, bottom - 10], [width * 0.55, middle + 10], [width * 0.64, cupRim], [width * 0.69, cupRim + 12], [width * 0.74, middle - 2], [width * 0.79, cupRim + 3], [width * 0.83, top + 8]];
        curved = true;
        this.keyLine(context, "杯口阻力", cupRim, blue, width * 0.80);
    } else if (type === "dormant_bottom" || type === "latent_bottom") {
        path = [[left, middle + 20], [width * 0.20, middle + 24], [width * 0.30, middle + 18], [width * 0.40, middle + 22], [width * 0.50, middle + 16], [width * 0.60, middle + 19], [width * 0.70, middle + 12], [width * 0.80, top + 14]];
        curved = true;
        this.keyLine(context, "平台阻力", middle + 8, blue, right);
      } else if (type === "v_top" || type === "v_bottom") {
        path = type === "v_top"
          ? [[left, bottom], [width * 0.28, middle + 12], [width * 0.48, top], [width * 0.60, middle - 6], [width * 0.79, bottom - 4]]
          : [[left, top], [width * 0.28, middle - 12], [width * 0.48, bottom], [width * 0.60, middle + 6], [width * 0.79, top + 4]];
      } else if (type === "uptrend") {
        path = [[left, bottom], [width * 0.22, middle + 18], [width * 0.32, bottom - 18], [width * 0.45, middle - 8], [width * 0.55, middle + 15], [width * 0.68, top + 16], [width * 0.76, top + 34], [width * 0.82, top + 8]];
        this.line(context, [[left, bottom], [width * 0.76, top + 35]], blue, 1.8, []);
        this.label(context, "上升支撑线", left + 3, bottom - 6, green);
      } else if (type === "downtrend") {
        path = [[left, top], [width * 0.22, middle - 18], [width * 0.32, top + 18], [width * 0.45, middle + 8], [width * 0.55, middle - 15], [width * 0.68, bottom - 16], [width * 0.76, bottom - 34], [width * 0.82, bottom - 8]];
        this.line(context, [[left, top], [width * 0.76, bottom - 35]], blue, 1.8, []);
        this.label(context, "下降阻力线", left + 3, top + 14, red);
      } else {
        path = [[left, middle], [width * 0.24, top], [width * 0.40, bottom], [width * 0.56, top + 12], [width * 0.72, bottom - 8], [right, middle]];
      }
      if (curved) {
        this.smoothLine(context, path, dark, 2.35);
      } else {
        this.line(context, path, dark, 2.2, []);
      }
      this.drawChartSignal(context, width, height, type);
    },

    smoothLine: function (context, points, color, width) {
      if (!points.length) {
        return;
      }
      context.strokeStyle = color;
      context.lineWidth = width || 2;
      context.setLineDash([]);
      context.beginPath();
      context.moveTo(points[0][0], points[0][1]);
      for (var i = 1; i < points.length - 1; i += 1) {
        var next = points[i + 1];
        var midX = (points[i][0] + next[0]) / 2;
        var midY = (points[i][1] + next[1]) / 2;
        context.quadraticCurveTo(points[i][0], points[i][1], midX, midY);
      }
      context.lineTo(points[points.length - 1][0], points[points.length - 1][1]);
      context.stroke();
    },

    drawChartSignal: function (context, width, height, type) {
      var accent = "#35bf78";
      var point = function (x, y, direction, label) {
        var startY = direction === "up" ? y + 24 : y - 24;
        this.signalArrow(context, x - 22, startY, x, y, accent, label);
        this.signalMarker(context, x, y, accent);
      }.bind(this);
      if (["double_bottom", "triple_bottom", "hs_bottom"].indexOf(type) >= 0) {
        point(width * 0.80, height * 0.38, "up", "买点");
      } else if (["double_top", "triple_top", "hs_top"].indexOf(type) >= 0) {
        point(width * 0.80, height * 0.70, "down", "卖点");
      } else if (type === "ascending_triangle") {
        point(width * 0.79, height * 0.20, "up", "买点");
      } else if (type === "descending_triangle") {
        point(width * 0.79, height * 0.80, "down", "卖点");
      } else if (type === "falling_wedge") {
        point(width * 0.79, height * 0.40, "up", "买点");
      } else if (type === "rising_wedge") {
        point(width * 0.79, height * 0.60, "down", "卖点");
      } else if (["round_bottom", "cup_with_handle", "cup_handle", "dormant_bottom", "latent_bottom", "v_bottom", "uptrend", "flag", "pennant"].indexOf(type) >= 0) {
        var buyY = height * 0.30;
        if (type === "round_bottom" || type === "cup_with_handle" || type === "cup_handle") {
          buyY = height * 0.17;
        } else if (type === "dormant_bottom" || type === "latent_bottom") {
          buyY = height * 0.49;
        } else if (type === "flag" || type === "pennant") {
          buyY = height * 0.38;
        }
        point(width * 0.81, buyY, "up", "买点");
      } else if (["round_top", "v_top", "downtrend"].indexOf(type) >= 0) {
        point(width * 0.81, height * 0.66, "down", "卖点");
      } else if (["symmetrical_triangle", "rectangle"].indexOf(type) >= 0) {
        point(width * 0.82, height * 0.28, "up", "买点");
        point(width * 0.82, height * 0.72, "down", "卖点");
      }
    },

    signalMarker: function (context, x, y, color) {
      context.strokeStyle = color;
      context.lineWidth = 1.2;
      context.strokeRect(x - 5, y - 5, 10, 10);
    },

    signalArrow: function (context, x1, y1, x2, y2, color, label) {
      var angle = Math.atan2(y2 - y1, x2 - x1);
      var size = 6;
      context.strokeStyle = color;
      context.fillStyle = color;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
      context.stroke();
      context.beginPath();
      context.moveTo(x2, y2);
      context.lineTo(x2 - size * Math.cos(angle - Math.PI / 6), y2 - size * Math.sin(angle - Math.PI / 6));
      context.lineTo(x2 - size * Math.cos(angle + Math.PI / 6), y2 - size * Math.sin(angle + Math.PI / 6));
      context.closePath();
      context.fill();
      context.font = '11px "DouyinSans", "Douyin Meihao", "PingFang SC", "Microsoft YaHei", sans-serif';
      context.textAlign = "right";
      context.fillText(label, x2, y2 < y1 ? y2 - 6 : y2 + 13);
      context.textAlign = "left";
    },

    keyLine: function (context, label, y, color, width) {
      this.line(context, [[12, y], [width - 12, y]], color, 1.5, []);
      this.label(context, label, 16, y - 7, color);
    },

    boundaries: function (context, upper, lower, width, red, green, blue) {
      this.line(context, upper, blue || "#2962ff", 1.55, []);
      this.line(context, lower, blue || "#2962ff", 1.55, []);
      this.label(context, "阻力", width - 46, upper[upper.length - 1][1] - 6, red);
      this.label(context, "支撑", width - 46, lower[lower.length - 1][1] + 14, green);
    }
  }
});
