const BASICS = [
  {
    name: "K线",
    group: "价格构成",
    definition: "一根K线记录一个周期内的开盘价、最高价、最低价和收盘价。",
    meaning: "实体反映开盘与收盘的力量结果，影线反映盘中曾经到达但未能保持的价格。",
    remember: "先看所处趋势和关键位置，再看单根K线长什么样。",
    diagram: "candle"
  },
  {
    name: "实体",
    group: "价格构成",
    definition: "开盘价与收盘价之间的矩形部分。",
    meaning: "实体越长，通常说明该周期内单方推动越明显；实体很小则表示犹豫。",
    remember: "实体大小应与该标的近期平均实体比较。",
    diagram: "body"
  },
  {
    name: "上影线",
    group: "价格构成",
    definition: "实体上沿到最高价之间的细线。",
    meaning: "表示价格曾经上冲，但一部分涨幅被卖盘压回。",
    remember: "长上影线位于上涨末端或阻力位附近时更值得关注。",
    diagram: "upper_shadow"
  },
  {
    name: "下影线",
    group: "价格构成",
    definition: "实体下沿到最低价之间的细线。",
    meaning: "表示价格曾经下探，但一部分跌幅被买盘收回。",
    remember: "长下影线位于下跌末端或支撑位附近时更有意义。",
    diagram: "lower_shadow"
  },
  {
    name: "阳线",
    group: "方向",
    definition: "收盘价高于开盘价的K线。本小程序按国内习惯显示为红色。",
    meaning: "表示这个周期结束时买方占优，但不代表下一周期一定上涨。",
    remember: "阳线必须结合位置、实体长度和成交量理解。",
    diagram: "bull_candle"
  },
  {
    name: "阴线",
    group: "方向",
    definition: "收盘价低于开盘价的K线。本小程序按国内习惯显示为绿色。",
    meaning: "表示这个周期结束时卖方占优，但不代表趋势已经反转。",
    remember: "趋势中的普通阴线与顶部转弱阴线含义不同。",
    diagram: "bear_candle"
  },
  {
    name: "最高价与最低价",
    group: "价格构成",
    definition: "最高价和最低价构成该周期实际交易过的完整价格范围。",
    meaning: "连续抬高的高低点构成上升结构，连续下移则构成下降结构。",
    remember: "技术图形主要由一系列有意义的高点和低点连接而成。",
    diagram: "high_low"
  },
  {
    name: "支撑位",
    group: "关键价位",
    definition: "价格回落时可能出现承接的区域，通常来自前低、平台、趋势线或缺口。",
    meaning: "支撑不是绝对底线，真正重要的是价格到达后是否止跌并重新走强。",
    remember: "有效跌破后，原支撑可能转化为阻力。",
    diagram: "support"
  },
  {
    name: "阻力位",
    group: "关键价位",
    definition: "价格上行时可能遇到抛压的区域，通常来自前高、平台或下降趋势线。",
    meaning: "放量突破并站稳后，原阻力可能转化为支撑。",
    remember: "不要只看盘中刺穿，优先观察收盘是否站稳。",
    diagram: "resistance"
  },
  {
    name: "颈线",
    group: "关键价位",
    definition: "双顶、双底、头肩形等反转图形中，用于确认结构是否完成的关键边界。",
    meaning: "图形轮廓出现并不等于成立，突破或跌破颈线才进入确认阶段。",
    remember: "颈线突破后的回踩表现通常比轮廓名称更重要。",
    diagram: "neckline"
  },
  {
    name: "缺口",
    group: "价格构成",
    definition: "相邻两根K线之间存在没有成交覆盖的价格区间。",
    meaning: "突破缺口常强化方向，中继缺口反映趋势延续，衰竭缺口可能接近趋势末段。",
    remember: "观察是否回补，以及回补后价格向哪一侧继续运行。",
    diagram: "gap"
  },
  {
    name: "成交量",
    group: "确认工具",
    definition: "一个周期内完成交易的数量，用于观察价格运动是否得到参与度支持。",
    meaning: "突破时量能扩大通常比无量突破更可靠，但不同市场需要使用各自的量能基准。",
    remember: "成交量用于确认，不应脱离价格结构独立下结论。",
    diagram: "volume"
  }
];

const INDICATOR_KNOWLEDGE = [
  {
    name: "移动平均线",
    displayName: "移动平均线（Moving Average）",
    group: "趋势工具",
    definition: "把最近一段时间的价格取平均并连成线，用来观察价格运行的方向和平均持仓成本。",
    meaning: "价格长期在线上方，通常说明趋势偏强；跌到均线附近时，要看能否获得承接，而不是把均线当成绝对底线。",
    parameters: "周期表示纳入多少根K线：周期越短反应越快，周期越长越平稳。日线的20表示20个交易日，周线的20表示20周。",
    source: "移动平均方法早已用于统计分析；Joseph Granville 在20世纪中期系统推广了均线交易法则。",
    remember: "均线会滞后，只反映已经发生的价格，不保证未来一定沿原方向运行。"
  },
  {
    name: "单均线、双均线与三均线",
    displayName: "单、双、三均线",
    group: "均线方案",
    definition: "单均线用一条线过滤趋势；双均线比较快线和慢线；三均线再加入中期线，观察短、中、长期成本的排列。",
    meaning: "快线上穿慢线称为金叉，向下跌破称为死叉。三线由短到长依次向上排列时，趋势通常更整齐。",
    parameters: "每个数字都是一条均线的周期。快线数字最小、慢线数字最大；周期必须是整数，不存在9.5日均线。",
    source: "属于移动平均线交易体系的常见应用，Granville 法则奠定了均线与价格关系的分析框架。",
    remember: "交叉过多往往代表震荡，不能只凭一次金叉或死叉行动。"
  },
  {
    name: "中间线",
    displayName: "中间线（价格中心趋势）",
    group: "均线无忧",
    definition: "用长期价格拟合出穿过行情中部的中心趋势线，像一根签子穿过一串糖葫芦，用于观察价格围绕什么节奏波动。",
    meaning: "价格在中间线上方代表高于长期中心，在下方代表低于长期中心；它与托底性质的便宜线、无忧线不是一回事。",
    parameters: "系统使用长期价格趋势估计中间线，并给出当前乖离率的历史分位，同时用箭头提示偏离后的统计回拉方向。",
    source: "基于普通最小二乘趋势拟合，是统计学中的经典线性估计方法。",
    remember: "中间线描述中心节奏，不直接给出买卖结论。"
  },
  {
    name: "银山谷",
    displayName: "银山谷（5/10/30日均线参考）",
    group: "均线形态",
    definition: "在下跌或筑底后的早期，5日、10日、30日均线先后向上交叉并形成短中长期多头排列，常被画成尖头向上的不规则三角形。",
    meaning: "它是国内均线图解中的早期转强参考，底部位置出现时说明短中长期成本关系开始改善。",
    parameters: "本项目默认用5日、10日、30日简单移动平均线寻找参考点；不同市场和周期可以使用其他短、中、长参数。",
    source: "国内技术分析资料常称为银山谷或价托；国际技术分析更常把底层逻辑归入三重均线向上交叉与多头排列，而不普遍使用“银山谷”这个名称。",
    remember: "银山谷不是确定买点，震荡市场中均线交叉容易反复，必须结合趋势位置和后续确认。"
  },
  {
    name: "金山谷",
    displayName: "金山谷（银山谷后的再次转强）",
    group: "均线形态",
    definition: "银山谷之后，价格经历回调或整理，再次出现5日、10日、30日均线向上交叉并形成多头排列的参考形态。",
    meaning: "它通常比第一次银山谷更晚，反映回调后再次转强；本项目只标记结构出现，不把它当成收益保证。",
    parameters: "仍使用5日、10日、30日简单移动平均线，并要求第二次多头排列出现在第一次之后且位置不明显更低。",
    source: "“金山谷”是国内均线形态的流传称呼；国际上可对应为回调后的再次三重均线看涨交叉或趋势延续确认。",
    remember: "金山谷与银山谷的区别主要在先后顺序，名称本身不是国际统一标准。"
  },
  {
    name: "乖离率",
    displayName: "乖离率（BIAS）",
    group: "风险温度",
    definition: "衡量当前价格离参考线有多远。数值为正表示价格在线上方，为负表示在线下方。",
    meaning: "乖离过大可理解为价格短期偏热，乖离很低则表示处于历史偏冷位置；系统还会给出当前乖离在历史中的分位。",
    parameters: "参考线决定比较基准，回看区间决定历史分位。周期越长，观察的是越长期的冷热程度。",
    source: "由价格与移动平均或趋势基准的距离演化而来，是技术分析中常见的偏离度量。",
    remember: "偏热不等于马上下跌，偏冷也不等于马上反弹，仍要看长期结构是否完好。"
  },
  {
    name: "盈利因子",
    displayName: "盈利因子（Profit Factor）",
    group: "回测指标",
    definition: "历史回测中全部盈利之和除以全部亏损绝对值，用来比较不同参数在过去的盈亏质量。",
    meaning: "大于1说明历史总盈利超过总亏损，数值越高通常越好，但交易次数太少时可能只是偶然。",
    parameters: "最小交易次数用于过滤样本太少的方案；回看年限越长，检验覆盖的市场阶段越多。",
    source: "属于交易系统评估中的常用统计量。",
    remember: "盈利因子是历史统计，不是未来收益承诺。"
  },
  {
    name: "MACD",
    displayName: "MACD（指数平滑异同移动平均线）",
    group: "趋势指标",
    definition: "比较快、慢两条指数移动平均线的差，再用一条信号线平滑，观察趋势动能是否增强或减弱。",
    meaning: "快线向上穿过信号线常称金叉，向下穿过称死叉；零轴上方通常代表中期趋势较强。",
    parameters: "经典12、26、9表示快线看12期、慢线看26期、信号线再平滑9期。数字越小越灵敏，也越容易出现反复信号。",
    source: "由美国技术分析师 Gerald Appel 在20世纪70年代提出并推广。",
    remember: "MACD适合看趋势变化，震荡行情中金叉和死叉可能频繁失效。"
  },
  {
    name: "KD与KDJ",
    displayName: "KD / KDJ（随机指标）",
    group: "摆动指标",
    definition: "比较收盘价在近期最高价和最低价区间中的位置，观察买卖力量是否进入偏强或偏弱区域。",
    meaning: "K、D从低位向上常用于观察反弹，从高位向下常用于观察转弱；J线放大变化，反应更快也更容易过度波动。",
    parameters: "9、3、3表示先观察9期高低区间，再分别用3期平滑K和D。第一项越大，指标越稳；越小，反应越快。",
    source: "随机指标通常归功于 George Lane；J线是后来广泛使用的扩展，在中国市场软件中尤其常见。",
    remember: "强趋势里指标可以长时间停在高位或低位，超买不等于立即卖出，超卖也不等于立即买入。"
  },
  {
    name: "RSI",
    displayName: "RSI（相对强弱指标）",
    group: "摆动指标",
    definition: "比较一段时间内上涨和下跌的平均力度，把结果压缩到0至100之间。",
    meaning: "30附近常作偏弱观察区，70附近常作偏热观察区；50以上通常偏强，50以下通常偏弱。",
    parameters: "14表示观察最近14期。周期短更敏感，周期长更平滑；系统会按历史表现比较不同整数周期。",
    source: "由 J. Welles Wilder Jr. 于1978年在《New Concepts in Technical Trading Systems》中提出。",
    remember: "上涨趋势中的RSI可以长期高于70，因此高位只代表风险升温，不是自动卖出。"
  },
  {
    name: "SuperTrend",
    displayName: "SuperTrend（超级趋势）",
    group: "趋势指标",
    definition: "用真实波幅衡量市场波动，再把波动距离放到价格上方或下方，形成随趋势切换的跟踪线。",
    meaning: "线在价格下方时用于观察多头趋势，在价格上方时用于观察空头趋势；价格穿越跟踪线后方向可能切换。",
    parameters: "ATR周期决定波动参考长度，倍数决定跟踪线离价格多远。倍数小更敏感，倍数大更稳但转向更慢。",
    source: "核心建立在 Wilder 提出的 ATR 真实波幅上；目前流行的 SuperTrend 版本常与 Olivier Seban 的推广相关。",
    remember: "它是趋势跟踪工具，横盘时也可能反复切换。"
  },
  {
    name: "信息离散度",
    displayName: "信息离散度（Information Discreteness）",
    group: "特色指标",
    definition: "观察一段涨跌是由少数几天突然完成，还是由许多天持续、缓慢地累积。",
    meaning: "同样的区间涨跌幅，可能由少数交易日突然完成，也可能由较多交易日逐步累积。系统用自然语言说明历史变化是集中、连续还是交错分散。",
    parameters: "回看窗口决定观察多长时间；指标结合上涨天数、下跌天数和区间总收益描述信息进入价格的方式。",
    source: "来自 Da、Gurun 与 Warachka 的论文《Frog in the Pan: Continuous Information and Momentum》。",
    remember: "它只描述历史涨跌在时间上的集中或分散程度，不评价资产优劣，不直接给出操作信号，也不预测未来涨跌。"
  },
  {
    name: "基础模式与自适应模式",
    displayName: "基础模式与自适应模式",
    group: "计算方式",
    definition: "基础模式平等检验所选历史区间；自适应模式会更重视与当前波动和趋势节奏相似的历史阶段。",
    meaning: "基础模式更透明、容易复核；自适应模式更贴近当前市场性格，但仍然只是历史比较。",
    parameters: "回看年限决定候选历史范围，方案类型决定比较单线、双线或三线。",
    source: "本项目根据历史相似行情与参数稳定性设计的两种计算方式。",
    remember: "两种模式结果可能不同；差异较大时，应优先查看图表和详细回测，而不是盲选数值更高者。"
  }
];

const CANDLE_ROWS = [
  ["十字星", "simple", "neutral", "开盘与收盘非常接近，实体很小。", "多空暂时平衡，本身不等于反转。", "处在趋势末端并由后续K线突破确认。"],
  ["长十字星", "simple", "neutral", "实体很小而上下影线明显较长。", "盘中波动激烈，最终仍回到开盘附近。", "结合前置趋势和后续收盘方向。"],
  ["螺旋桨", "simple", "neutral", "实体较小，同时有明显的上、下影线；它比真正的十字星保留了更清楚的实体。", "多空争夺加剧，趋势可能进入犹豫阶段。", "等待区间被有效突破，不把螺旋桨直接当作十字星。"],
  ["射击之星", "simple", "bear", "上涨后出现小实体和长上影线，下影线很短；实体可以是阳线或阴线。", "冲高被卖盘压回，是潜在顶部警报。", "后续跌破星线实体或低点。"],
  ["锤子线", "simple", "bull", "下跌后出现小实体和长下影线，上影线很短。", "低位抛压被买方收回，是潜在止跌线索。", "后续上涨并守住锤子线低点。"],
  ["倒锤头线", "simple", "bull", "下跌后出现小实体和长上影线。", "买方曾主动上攻，但尚未完全占优。", "下一根K线继续走强。"],
  ["吊颈线", "simple", "bear", "上涨后出现小实体和长下影线。", "外形像锤头，但高位语境使其成为风险警报。", "后续下跌确认，而不是只凭外形判断。"],
  ["T字线", "simple", "bull", "开盘与收盘接近最高价，下影线明显。", "盘中下探后被收回，低位时偏向承接增强。", "观察后续是否站上附近阻力。"],
  ["倒T字线", "simple", "bear", "开盘与收盘接近最低价，上影线明显。", "盘中上冲失败，高位时偏向压力增强。", "观察后续是否跌破附近支撑。"],
  ["一字线", "simple", "neutral", "开盘、最高、最低和收盘非常接近。", "常见于涨跌停或流动性不足，普通形态解释并不适用。", "先判断交易制度和成交状态。"],
  ["曙光初现", "simple", "bull", "下跌后先出现较长阴线，随后阳线低开或贴近前一收盘，收盘深入前一阴线实体的一半以上。", "买方开始夺回失地，是底部反攻线索。", "后续守住组合低点并继续走强；别把单根长阳直接命名为曙光初现。"],
  ["乌云盖顶", "simple", "bear", "上涨后先出现较长阳线，随后阴线高开或明显冲高，收盘深入前一阳线实体的一半以上。", "卖方在高位明显反攻，是顶部转弱线索。", "后续跌破组合低点；射击之星本身不能替代乌云盖顶。"],
  ["看涨吞没", "simple", "bull", "下降或回调后，后一根阳线实体完整覆盖前一根阴线实体。", "低位时说明买方反攻力度增强。", "前面存在下降趋势，之后继续上涨。"],
  ["看跌吞没", "simple", "bear", "上涨或反弹后，后一根阴线实体完整覆盖前一根阳线实体。", "高位时说明卖方反攻力度增强。", "前面存在上涨趋势，之后继续下跌。"],
  ["看涨孕线", "simple", "bull", "长阴线后出现被前一实体完全包住的小实体，又称看涨身怀六甲。", "下跌动能收缩，可能进入止跌观察。", "后续向上突破母线范围。"],
  ["看跌孕线", "simple", "bear", "长阳线后出现被前一实体完全包住的小实体，又称看跌身怀六甲。", "上涨动能收缩，可能进入转弱观察。", "后续向下突破母线范围。"],
  ["好友反攻", "simple", "bull", "下降趋势中先出现阴线，次日明显低开后收阳，且两根K线的收盘价近似相同。", "低开抛压被买方完全收回，说明低位承接增强。", "下一根K线继续走高并站上组合高点。"],
  ["淡友反攻", "simple", "bear", "上升趋势中先出现阳线，次日明显高开后收阴，且两根K线的收盘价近似相同。", "高开买盘被卖方完全压回，说明高位压力增强。", "下一根K线继续走弱并跌破组合低点。"],
  ["旭日东升", "simple", "bull", "下降末端先出现阴线，次日阳线开盘位于前一阴线实体内部，收盘越过前一阴线开盘并高于其最高价。", "开盘后的抛压被快速吸收，买方形成强力反攻。", "后续不重新跌回组合低点。"],
  ["倾盆大雨", "simple", "bear", "上升末端先出现阳线，次日阴线开盘位于前一阳线实体内部，收盘跌破前一阳线开盘并低于其最低价。", "开盘后的追涨力量被快速反压，卖方形成强力反攻。", "后续不能迅速收复阴线实体。"],
  ["高开出逃", "trend", "bear", "价格突然远高于前一交易区间开盘，随后一路走弱并以长阴线收在低位。", "高开未获得承接，常反映资金借高位退出。", "后续跌破当日低点，且高开位置转为压力。"],
  ["下探上涨", "trend", "bull", "价格突然远低于前一交易区间开盘，随后迅速走强并以长阳线收在高位。", "低开抛压被快速吸收，买方重新占优。", "后续守住当日低点和强阳线主要支撑。"],
  ["平顶", "simple", "bear", "相邻K线形成近似相同的高点。", "说明同一压力区域两次限制上涨。", "后续向下离开压力区。"],
  ["平底", "simple", "bull", "相邻K线形成近似相同的低点。", "说明同一支撑区域两次获得承接。", "后续向上离开支撑区。"],
  ["搓揉线", "simple", "neutral", "连续K线出现明显上下影线，实体较小。", "多空在高位或低位反复争夺。", "依据所在趋势等待方向突破。"],
  ["尽头线", "simple", "neutral", "趋势末段的小K线被前一根长影线范围限制。", "原方向推进受阻，可能接近阶段性尽头。", "必须由相反方向K线确认。"],
  ["早晨之星", "composite", "bull", "长阴、小实体、长阳构成三根底部组合。", "卖方动能减弱后买方接管。", "出现在下降末端，第三根阳线深入首根阴线。"],
  ["黄昏之星", "composite", "bear", "长阳、小实体、长阴构成三根顶部组合。", "买方动能减弱后卖方接管。", "出现在上涨末端，第三根阴线深入首根阳线。"],
  ["早晨十字星", "composite", "bull", "早晨之星的中间K线为十字星。", "底部犹豫后买方反攻，警示性更强。", "第三根阳线和后续上涨共同确认。"],
  ["黄昏十字星", "composite", "bear", "黄昏之星的中间K线为十字星。", "顶部犹豫后卖方反攻。", "第三根阴线和后续下跌共同确认。"],
  ["红三兵", "composite", "bull", "三根阳线连续抬高收盘价；实体较长、收盘接近高位时属于强势变体，常称三个白色武士。", "反映买方稳步推进。", "低位或突破后出现，实体不过度缩短。"],
  ["三只乌鸦", "composite", "bear", "上涨后连续三根较长阴线逐步下移。", "顶部卖压连续释放。", "开盘位于前一实体附近且收盘不断创新低。"],
  ["黑三兵", "composite", "bear", "三根实体阴线连续降低收盘价。", "反映卖方持续推进。", "后续不能快速收复第三根阴线。"],
  ["下跌三连阴", "composite", "bear", "连续三根实体阴线，收盘依次降低。", "价格结构持续转弱。", "必须完整包含三根阴线，不能只圈两根。"],
  ["上升三法", "composite", "bull", "长阳之后数根小阴线整理，随后长阳向上突破。", "上涨中的短暂停顿后恢复原趋势。", "整理K线不有效跌破第一根长阳范围。"],
  ["下降三法", "composite", "bear", "长阴之后数根小阳线整理，随后长阴向下突破。", "下跌中的短暂停顿后恢复原趋势。", "整理K线不有效突破第一根长阴范围。"],
  ["高位并排阳线", "composite", "bull", "上升缺口后至少两根开盘接近的阳线并排。", "缺口未回补时偏向原趋势延续。", "必须包含多根阳线并保持缺口。"],
  ["低位并排阴线", "composite", "bear", "下降缺口后至少两根开盘接近的阴线并排。", "缺口未回补时偏向下跌延续。", "必须包含多根阴线并保持缺口。"],
  ["两只乌鸦", "composite", "bear", "上涨后出现跳空的小阴线和进一步转弱的阴线。", "高位连续受压，可能形成顶部。", "后续下破组合低点。"],
  ["多方尖兵", "composite", "bull", "首次上攻后整理，再由阳线突破前高。", "买方经过试探后重新推进。", "突破前高并保持在突破位上方。"],
  ["空方尖兵", "composite", "bear", "首次下探后整理，再由阴线跌破前低。", "卖方经过试探后重新推进。", "跌破前低并保持在突破位下方。"],
  ["倒三阳", "composite", "bear", "下降过程中连续收阳，但价格重心仍持续下移。", "表面收阳并不代表趋势转强。", "必须位于下降过程，不能与红三兵同时成立。"],
  ["塔形顶", "composite", "bear", "左侧强阳、顶部整理、右侧强阴构成完整顶部。", "上涨动能由强转弱。", "框住完整结构并等待下破整理区。"],
  ["塔形底", "composite", "bull", "左侧强阴、底部整理、右侧强阳构成完整底部。", "下跌动能衰减，买方接管。", "不能由两根阴线直接判定，需完整底部结构。"],
  ["岛形顶", "composite", "bear", "先上跳空、后下跳空，中间价格区间被孤立。", "顶部追涨资金被困，是较强反转警报。", "下跳空不被快速回补并继续走弱。"],
  ["岛形底", "composite", "bull", "先下跳空、后上跳空，中间价格区间被孤立。", "抛压释放后买方回归。", "上跳空不被快速回补且后续低点抬高。"],
  ["加速上升", "trend", "bull", "多个波段的上涨斜率和单位时间涨幅连续提高。", "趋势很强，末段也可能过热。", "不能由一根大阳线判定，需连续速率变化。"],
  ["加速下跌", "trend", "bear", "多个波段的下跌斜率和单位时间跌幅连续提高。", "卖压快速释放，结构明显转弱。", "不能与同一区间的绵绵阴跌同时成立。"],
  ["冉冉上升", "trend", "bull", "价格以较小实体和温和斜率持续抬高。", "买方稳定推进，波动相对克制。", "高点、低点逐步抬高且回撤有限。"],
  ["绵绵阴跌", "trend", "bear", "价格以较小实体和较低波动持续缓慢下移。", "买盘长期不足形成慢性弱势。", "高低点持续下移，反弹不能收复平台。"],
  ["徐缓上升", "trend", "bull", "上涨斜率较缓，价格重心有序抬高。", "趋势偏多但推进速度不快。", "主要低点不被破坏。"],
  ["徐缓下降", "trend", "bear", "下跌斜率较缓，价格重心有序下移。", "趋势偏弱但不是恐慌下跌。", "主要高点持续降低。"],
  ["稳步上涨", "trend", "bull", "价格沿稳定节奏抬高，回撤后仍恢复上涨。", "趋势结构健康。", "回撤守住上升趋势线或前期平台。"],
  ["稳步下跌", "trend", "bear", "价格沿稳定节奏下移，反弹后仍恢复下跌。", "空方持续占优。", "反弹受阻于下降趋势线或前期平台。"],
  ["升势受阻", "trend", "bear", "上涨过程中阳线实体缩短或上影增多，推进开始受阻。", "买方动能下降，可能转入整理或回调。", "后续跌破短期支撑。"],
  ["跌势受阻", "trend", "bull", "下跌过程中阴线实体缩短或下影增多，推进开始受阻。", "卖方动能下降，可能转入整理或反弹。", "后续突破短期阻力。"]
];

const CHART_ROWS = [
  ["上升趋势线", "bull", "连接两个或更多有意义的上升低点。", "趋势线附近是动态支撑观察区。", "有效跌破后原上升节奏可能被破坏。", "uptrend"],
  ["下降趋势线", "bear", "连接两个或更多有意义的下降高点。", "趋势线附近是动态阻力观察区。", "有效突破后下降节奏可能改变。", "downtrend"],
  ["双顶", "bear", "价格两次冲击相近高位未能继续上涨。", "两个顶部之间的低点形成颈线。", "跌破颈线后才进入确认阶段。", "double_top"],
  ["双底", "bull", "价格两次下探相近低位并获得承接。", "两个底部之间的高点形成颈线。", "突破颈线后才进入确认阶段。", "double_bottom"],
  ["三重顶", "bear", "价格三次测试相近阻力区域均未能突破。", "多次受阻说明上方供给较强。", "跌破整理区颈线确认。", "triple_top"],
  ["三重底", "bull", "价格三次测试相近支撑区域均获得承接。", "多次承接说明下方需求较强。", "突破整理区颈线确认。", "triple_bottom"],
  ["头肩顶", "bear", "左肩、较高的头部和右肩构成顶部轮廓。", "左右低点连接为颈线。", "跌破颈线并观察回抽是否受阻。", "hs_top"],
  ["头肩底", "bull", "左肩、较低的头部和右肩构成底部轮廓。", "左右反弹高点连接为颈线。", "突破颈线并观察回踩是否企稳。", "hs_bottom"],
  ["上升三角形", "bull", "高点受水平阻力限制，低点逐步抬高。", "买方持续抬高承接位置。", "向上突破阻力并站稳后确认。", "ascending_triangle"],
  ["下降三角形", "bear", "低点受水平支撑限制，高点逐步降低。", "卖方持续压低反弹高度。", "向下跌破支撑并保持后确认。", "descending_triangle"],
  ["对称三角形", "neutral", "高点降低、低点抬高，波动区间逐步收敛。", "多空力量暂时压缩，方向尚未确定。", "等待价格突破任一边界。", "symmetrical_triangle"],
  ["矩形整理", "neutral", "价格在近似水平的支撑与阻力之间反复运行。", "市场处于方向选择阶段。", "突破边界后观察回踩和成交量。", "rectangle"],
  ["上升楔形", "bear", "支撑线和阻力线同时向上，但两线逐渐收敛。", "价格仍上涨，但推进空间和动能可能收缩。", "跌破下方支撑线后偏向转弱。", "rising_wedge"],
  ["下降楔形", "bull", "支撑线和阻力线同时向下，但两线逐渐收敛。", "价格仍下跌，但卖压可能逐步衰减。", "突破上方阻力线后偏向转强。", "falling_wedge"],
  ["旗形", "neutral", "快速趋势之后出现倾斜的小型平行整理通道。", "通常被视为原趋势中的短暂停顿。", "突破旗面边界且方向与旗杆一致。", "flag"],
  ["三角旗形", "neutral", "快速趋势之后出现小型收敛三角整理。", "多空短暂平衡，等待原方向恢复或失败。", "突破三角边界并结合旗杆方向确认。", "pennant"],
  ["圆顶", "bear", "价格重心由上升逐渐转为下降，顶部呈弧形。", "趋势变化缓慢，常没有单一明确转折日。", "跌破弧形底部附近支撑。", "round_top"],
  ["圆底", "bull", "价格重心由下降逐渐转为上升，底部呈弧形。", "供需关系逐步改善。", "突破弧形上沿附近阻力。", "round_bottom"],
  ["茶杯柄", "bull", "价格先形成圆弧杯底，右侧回到前高附近后出现短暂温和回撤，随后向上突破杯口阻力。", "长期整理后买方逐步接管，柄部回撤是突破前的最后整理。", "杯口阻力被有效突破并收盘站稳；突破前不预设买点。", "cup_with_handle"],
  ["潜伏底", "bull", "价格经过长期下跌后在狭窄区间低波动横盘，随后逐步放量并向上突破平台。", "长期潜伏说明抛压逐渐衰竭，突破平台后才进入结构确认。", "平台上沿被有效突破并收盘站稳；突破前不预设买点。", "dormant_bottom"],
  ["V形顶", "bear", "快速上涨后几乎不经整理就快速下跌。", "情绪和方向在短时间内剧烈反转。", "跌破反转点附近支撑并保持弱势。", "v_top"],
  ["V形底", "bull", "快速下跌后几乎不经整理就快速上涨。", "恐慌释放后买方迅速接管。", "突破反转点附近阻力并保持强势。", "v_bottom"]
];

const CANDLE_PATTERNS = CANDLE_ROWS.map(function (row) {
  return {
    name: row[0],
    category: row[1],
    direction: row[2],
    definition: row[3],
    meaning: row[4],
    confirmation: row[5],
    diagram: "pattern:" + row[0],
    sourceLabel: "传统K线分析"
  };
});

const DISPLAY_NAMES = {
  "十字星": "十字星 (Doji)",
  "长十字星": "长十字星 (Long-legged Doji)",
  "螺旋桨": "螺旋桨 (Spinning Top)",
  "射击之星": "射击之星 / 流星线 (Shooting Star)",
  "锤子线": "锤子线 (Hammer)",
  "倒锤头线": "倒锤头线 (Inverted Hammer)",
  "吊颈线": "吊颈线 (Hanging Man)",
  "T字线": "T字线 / 蜻蜓十字星 (Dragonfly Doji)",
  "倒T字线": "倒T字线 / 倒十字线 (Gravestone Doji)",
  "一字线": "一字线 (Four-price Doji)",
  "曙光初现": "曙光初现 / 刺透形态 / 斩回线 (Piercing Pattern)",
  "乌云盖顶": "乌云盖顶 (Dark Cloud Cover)",
  "看涨吞没": "看涨吞没 / 穿头破脚 (Bullish Engulfing)",
  "看跌吞没": "看跌吞没 / 穿头破脚 (Bearish Engulfing)",
  "看涨孕线": "看涨孕线 / 身怀六甲（看涨） (Bullish Harami)",
  "看跌孕线": "看跌孕线 / 身怀六甲（看跌） (Bearish Harami)",
  "好友反攻": "好友反攻 (Bullish Counterattack)",
  "淡友反攻": "淡友反攻 (Bearish Counterattack)",
  "旭日东升": "旭日东升 (Rising Sun)",
  "倾盆大雨": "倾盆大雨 (Downpour)",
  "高开出逃": "高开出逃 (Gap-up Failure)",
  "下探上涨": "下探上涨 (Gap-down Recovery)",
  "尽头线": "尽头线 (End Line)",
  "岛形顶": "岛形顶 (Island Top)",
  "岛形底": "岛形底 (Island Bottom)",
  "茶杯柄": "茶杯柄 (Cup and Handle)",
  "潜伏底": "潜伏底 (Dormant Bottom)",
  "红三兵": "红三兵 / 三个白色武士（强势变体） (Three White Soldiers)"
};

const ENGLISH_NAMES = {
  "平顶": "Tweezers Top",
  "平底": "Tweezers Bottom",
  "搓揉线": "High-wave Candles",
  "早晨之星": "Morning Star",
  "黄昏之星": "Evening Star",
  "早晨十字星": "Morning Doji Star",
  "黄昏十字星": "Evening Doji Star",
  "三只乌鸦": "Three Black Crows",
  "黑三兵": "Black Three Soldiers",
  "下跌三连阴": "Three Consecutive Bearish Candles",
  "上升三法": "Rising Three Methods",
  "下降三法": "Falling Three Methods",
  "高位并排阳线": "Upside Gap Side-by-side White Lines",
  "低位并排阴线": "Downside Gap Side-by-side Black Lines",
  "两只乌鸦": "Two Crows",
  "多方尖兵": "Bullish Advance Guard",
  "空方尖兵": "Bearish Advance Guard",
  "倒三阳": "Three Countertrend Bullish Candles",
  "塔形顶": "Tower Top",
  "塔形底": "Tower Bottom",
  "加速上升": "Accelerating Rise",
  "加速下跌": "Accelerating Decline",
  "冉冉上升": "Gradual Rise",
  "绵绵阴跌": "Persistent Decline",
  "徐缓上升": "Slow Rise",
  "徐缓下降": "Slow Decline",
  "稳步上涨": "Steady Uptrend",
  "稳步下跌": "Steady Downtrend",
  "升势受阻": "Stalled Advance",
  "跌势受阻": "Stalled Decline",
  "上升趋势线": "Uptrend Line",
  "下降趋势线": "Downtrend Line",
  "双顶": "Double Top",
  "双底": "Double Bottom",
  "三重顶": "Triple Top",
  "三重底": "Triple Bottom",
  "头肩顶": "Head and Shoulders Top",
  "头肩底": "Inverse Head and Shoulders",
  "上升三角形": "Ascending Triangle",
  "下降三角形": "Descending Triangle",
  "对称三角形": "Symmetrical Triangle",
  "矩形整理": "Rectangle",
  "上升楔形": "Rising Wedge",
  "下降楔形": "Falling Wedge",
  "旗形": "Flag",
  "三角旗形": "Pennant",
  "圆顶": "Rounding Top",
  "圆底": "Rounding Bottom",
  "V形顶": "V-shaped Top",
  "V形底": "V-shaped Bottom"
};

function displayNameFor(name) {
  return DISPLAY_NAMES[name] || (ENGLISH_NAMES[name] ? name + " (" + ENGLISH_NAMES[name] + ")" : name);
}

const NAME_ALIASES = {
  "锤头线": "锤子线",
  "射击之星 / 流星线": "射击之星",
  "流星线": "射击之星",
  "长脚十字星": "长十字星",
  "倒十字线": "倒T字线",
  "蜻蜓十字星": "T字线",
  "墓碑十字星": "倒T字线",
  "刺透技术形态": "曙光初现",
  "斩回线": "曙光初现",
  "高开逃逸": "高开出逃",
  "低开突涨": "下探上涨",
  "三个白色武士": "红三兵",
  "空方反攻": "淡友反攻",
  "弹友反攻": "淡友反攻"
};

CANDLE_PATTERNS.forEach(function (item) {
  item.displayName = displayNameFor(item.name);
});

const CHART_PATTERNS = CHART_ROWS.map(function (row) {
  var tradeHint = row[1] === "bull"
    ? "价格有效突破阻力或颈线后，回踩守住可作为参考买点。"
    : row[1] === "bear"
      ? "价格有效跌破支撑或颈线后，反抽受阻可作为参考卖点。"
      : "向上有效突破是参考买点，向下有效跌破是参考卖点，突破前不预设方向。";
  return {
    name: row[0],
    category: "chart",
    direction: row[1],
    definition: row[2],
    meaning: row[3],
    confirmation: row[4],
    diagram: row[5],
    displayName: displayNameFor(row[0]),
    tradeHint: tradeHint,
    sourceLabel: "经典技术图形"
  };
});

const KNOWLEDGE_MAP = {};
CANDLE_PATTERNS.forEach(function (item) {
  KNOWLEDGE_MAP[item.name] = item;
});
CHART_PATTERNS.forEach(function (item) {
  KNOWLEDGE_MAP[item.name] = item;
});

function fallback(name, category, direction) {
  return {
    name: name,
    category: category || "simple",
    direction: direction || "neutral",
    definition: name + "由价格、实体、影线或连续波段共同构成。",
    meaning: "形态含义取决于趋势位置、关键价位和后续确认。",
    confirmation: "结合前置趋势、关键边界和后续K线确认。",
    sourceLabel: "传统技术分析"
  };
}

function getKnowledge(name, category, direction) {
  var base = String(name || "形态").split("·")[0];
  if (base === "身怀六甲") {
    base = direction === "bear" ? "看跌孕线" : "看涨孕线";
  }
  base = NAME_ALIASES[base] || base;
  return KNOWLEDGE_MAP[base] || fallback(base, category, direction);
}

function candlePatterns() {
  return CANDLE_PATTERNS.slice();
}

function chartPatterns() {
  return CHART_PATTERNS.slice();
}

function basics() {
  return BASICS.slice();
}

function indicators() {
  return INDICATOR_KNOWLEDGE.slice();
}

function allKnowledge() {
  return CANDLE_PATTERNS.concat(CHART_PATTERNS, INDICATOR_KNOWLEDGE);
}

module.exports = {
  getKnowledge: getKnowledge,
  allKnowledge: allKnowledge,
  basics: basics,
  indicators: indicators,
  candlePatterns: candlePatterns,
  chartPatterns: chartPatterns
};
