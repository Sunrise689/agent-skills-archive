Page({
  copyEmail: function () {
    wx.setClipboardData({
      data: "yuanxing@coze.email",
      success: function () {
        wx.showToast({ title: "邮箱已复制", icon: "success" });
      }
    });
  }
});
