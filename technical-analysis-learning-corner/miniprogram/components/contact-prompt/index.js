Component({
  data: { visible: true },
  lifetimes: {
    attached: function () {
      var component = this;
      var pages = getCurrentPages();
      var current = pages.length ? pages[pages.length - 1].route : "";
      if (current === "pages/contact/contact") {
        component.setData({ visible: false });
        return;
      }
      component.showPrompt();
      component.promptTimer = setInterval(function () { component.showPrompt(); }, 30000);
    },
    detached: function () {
      clearInterval(this.promptTimer);
      clearTimeout(this.hideTimer);
    }
  },
  methods: {
    showPrompt: function () {
      var component = this;
      clearTimeout(this.hideTimer);
      this.setData({ visible: true });
      this.hideTimer = setTimeout(function () { component.setData({ visible: false }); }, 9000);
    },
    close: function () {
      clearTimeout(this.hideTimer);
      this.setData({ visible: false });
    },
    open: function () {
      var pages = getCurrentPages();
      if (pages.length && pages[pages.length - 1].route === "pages/contact/contact") return;
      wx.navigateTo({ url: "/pages/contact/contact" });
    }
  }
});
