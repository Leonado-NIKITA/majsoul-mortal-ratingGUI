// 注入牌谱屋页面: 记下页面自己请求到的 player_records 结果 (页面已自行通过牌谱屋的人机验证).
// 安卓 WebView 只能在页面加载后执行脚本, 所以同时包装 fetch 和 XHR, 重复注入是安全的.
(function () {
  if (window.__mjr) return "already";
  var store = {};
  var n = 0;
  function add(url, text) {
    if (String(url).indexOf("player_records") < 0) return;
    try {
      var arr = JSON.parse(text);
      if (!Array.isArray(arr)) return;
      arr.forEach(function (r) { if (r && r.uuid) { store[r.uuid] = r; } });
      n++;
    } catch (e) { /* 非 JSON (例如 429 提示) 忽略 */ }
  }
  var of = window.fetch;
  if (of) {
    window.fetch = function (input, init) {
      return of.apply(this, arguments).then(function (resp) {
        try {
          var u = typeof input === "string" ? input : (input && input.url) || "";
          if (u.indexOf("player_records") >= 0 && resp.ok) {
            resp.clone().text().then(function (t) { add(u, t); });
          }
        } catch (e) { /* ignore */ }
        return resp;
      });
    };
  }
  var oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__mjrUrl = u;
    this.addEventListener("load", function () {
      if (this.status === 200) {
        try { add(this.__mjrUrl, this.responseText); } catch (e) { /* ignore */ }
      }
    });
    return oo.apply(this, arguments);
  };
  window.__mjr = {
    stat: function () { return { responses: n, records: Object.keys(store).length }; },
    take: function () {
      var out = Object.keys(store).map(function (k) { return store[k]; });
      return JSON.stringify(out);
    },
    clear: function () { store = {}; n = 0; }
  };
  return "installed";
})();
