const config = require("./config");

App({
  onLaunch: function () {
    if (config.cloudEnvId && wx.cloud) {
      wx.cloud.init({
        env: config.cloudEnvId,
        traceUser: true
      });
    }
    this.loadDouyinFont();
  },
  loadDouyinFont: function () {
    var app = this;
    var url = String(config.douyinFontUrl || "").trim();
    if (!/^https:\/\//i.test(url) || !wx.loadFontFace) {
      return;
    }
    wx.loadFontFace({
      family: "DouyinSans",
      source: 'url("' + url.replace(/"/g, "") + '")',
      global: true,
      success: function () {
        app.globalData.douyinFontReady = true;
      },
      fail: function () {
        // The system font fallback remains readable.  Deployment verification
        // records the URL/CORS failure without blocking app launch.
        app.globalData.douyinFontReady = false;
      }
    });
  },
  globalData: {
    apiBaseUrl: config.apiBaseUrl,
    cloudEnvId: config.cloudEnvId,
    cloudServiceName: config.cloudServiceName,
    douyinFontReady: false,
    analysis: null
  }
});
