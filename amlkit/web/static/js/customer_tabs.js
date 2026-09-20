(function () {
  var container = document.getElementById('customer-tabs');
  var hasAlerts = container && container.dataset.hasAlerts === 'true';
  var tabs = ['overview', 'alerts', 'monitoring', 'casefile', 'history'];

  window.switchTab = function (id) {
    tabs.forEach(function (t) {
      var panel = document.getElementById('tab-' + t);
      var link = document.querySelector('[data-tab="' + t + '"]');
      if (t === id) {
        panel.style.display = 'block';
        link.classList.add('on');
      } else {
        panel.style.display = 'none';
        link.classList.remove('on');
      }
    });
    history.replaceState(null, '', '#' + id);
  };

  var hash = location.hash.slice(1);
  var initial = tabs.indexOf(hash) !== -1 ? hash : (hasAlerts ? 'alerts' : 'overview');
  switchTab(initial);
}());
