"use strict";

var CATEGORY_KEYS = ["simple", "composite", "trend", "chart", "gap"];
var CATEGORY_LIMITS = {
  simple: 10,
  composite: 8,
  trend: 7,
  chart: 4,
  gap: 4
};

function categoryOf(item) {
  var value = String(item && item.category || "simple");
  return CATEGORY_KEYS.indexOf(value) >= 0 ? value : "simple";
}

function eventKey(item) {
  return [
    item && (item.pattern_id || item.pattern || item.name || "unknown"),
    Number(item && item.start || 0),
    Number(item && (item.end !== undefined ? item.end : item.start) || 0),
    String(item && item.direction || "neutral")
  ].join(":");
}

function eventIsVisible(item, eventVisibility) {
  return !eventVisibility || eventVisibility[item.id] !== false;
}

function eligible(item, visibility, autoIdentify, eventVisibility) {
  if (!eventIsVisible(item, eventVisibility)) return false;
  var automatic = autoIdentify === true && item.autoSelected === true;
  var manual = visibility && visibility[categoryOf(item)] === true;
  return automatic || manual;
}

function stateRank(item) {
  return {
    confirmed: 5,
    candidate: 3,
    detected: 2,
    degraded: 1
  }[String(item && item.state || "candidate")] || 0;
}

function rankTuple(item, autoIdentify) {
  return [
    autoIdentify === true && item.autoSelected === true ? 1 : 0,
    Number(item && item.end || 0),
    stateRank(item),
    Number(item && item.confidence || 0),
    Math.max(1, Number(item && item.end || 0) - Number(item && item.start || 0) + 1)
  ];
}

function compareRank(left, right, autoIdentify) {
  var a = rankTuple(left, autoIdentify);
  var b = rankTuple(right, autoIdentify);
  for (var index = 0; index < a.length; index += 1) {
    if (a[index] !== b[index]) return b[index] - a[index];
  }
  return eventKey(left).localeCompare(eventKey(right));
}

function uniqueEligible(patterns, visibility, autoIdentify, eventVisibility) {
  var seen = {};
  return (patterns || []).filter(function (item) {
    if (!eligible(item, visibility, autoIdentify, eventVisibility)) return false;
    var key = eventKey(item);
    if (seen[key]) return false;
    seen[key] = true;
    return true;
  });
}

function enabledManualCategories(visibility) {
  return CATEGORY_KEYS.filter(function (key) {
    return visibility && visibility[key] === true;
  });
}

function tooDense(item, selected) {
  var category = categoryOf(item);
  if (category === "chart") return false;
  var start = Number(item.start || 0);
  var end = Number(item.end !== undefined ? item.end : start);
  var center = (start + end) / 2;
  return selected.some(function (existing) {
    if (categoryOf(existing) !== category) return false;
    var existingStart = Number(existing.start || 0);
    var existingEnd = Number(existing.end !== undefined ? existing.end : existingStart);
    var existingCenter = (existingStart + existingEnd) / 2;
    var overlaps = Math.min(end, existingEnd) >= Math.max(start, existingStart);
    return overlaps || Math.abs(center - existingCenter) <= 1.5;
  });
}

function selectForCanvas(patterns, options) {
  options = options || {};
  var visibility = options.visibility || {};
  var autoIdentify = options.autoIdentify === true;
  var eligibleItems = uniqueEligible(
    patterns,
    visibility,
    autoIdentify,
    options.eventVisibility || {}
  );
  var manualCategories = enabledManualCategories(visibility);
  var overallLimit = manualCategories.length <= 1
    ? (manualCategories.length ? CATEGORY_LIMITS[manualCategories[0]] : 5)
    : 12;
  if (autoIdentify && manualCategories.length) overallLimit = Math.max(overallLimit, 12);

  var sorted = eligibleItems.slice().sort(function (left, right) {
    return compareRank(left, right, autoIdentify);
  });
  var selected = [];
  var selectedByCategory = {};
  CATEGORY_KEYS.forEach(function (key) { selectedByCategory[key] = 0; });

  sorted.forEach(function (item) {
    if (selected.length >= overallLimit) return;
    var category = categoryOf(item);
    var isAutomatic = autoIdentify && item.autoSelected === true;
    var categoryLimit = isAutomatic ? 5 : CATEGORY_LIMITS[category];
    if (selectedByCategory[category] >= categoryLimit) return;
    // Automatic results are already density-resolved by FAE.  Manual pools
    // are complete, so only their canvas projection needs local de-cluttering.
    if (!isAutomatic && tooDense(item, selected)) return;
    selected.push(item);
    selectedByCategory[category] += 1;
  });

  selected.sort(function (left, right) {
    return Number(left.start || 0) - Number(right.start || 0);
  });
  var totalsByCategory = {};
  CATEGORY_KEYS.forEach(function (key) { totalsByCategory[key] = 0; });
  eligibleItems.forEach(function (item) { totalsByCategory[categoryOf(item)] += 1; });
  return {
    visible: eligibleItems,
    drawn: selected,
    visibleTotal: eligibleItems.length,
    canvasTotal: selected.length,
    totalsByCategory: totalsByCategory,
    drawnByCategory: selectedByCategory
  };
}

module.exports = {
  CATEGORY_KEYS: CATEGORY_KEYS,
  CATEGORY_LIMITS: CATEGORY_LIMITS,
  categoryOf: categoryOf,
  eventKey: eventKey,
  eligible: eligible,
  selectForCanvas: selectForCanvas
};
