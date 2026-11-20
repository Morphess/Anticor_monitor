/* Compatibility glue for admin.js variants that only know users/departments. */
(function () {
  'use strict';
  const auditTab = document.getElementById('tab-audit');
  const auditPanel = document.getElementById('panel-audit');
  if (!auditTab || !auditPanel) return;

  const tabs = Array.from(document.querySelectorAll('.admin-tabs [data-tab]'));
  const panels = Array.from(document.querySelectorAll('.admin-workspace [data-panel]'));

  // Attach after admin.js so its click handling runs first; do not overwrite it.
  auditTab.addEventListener('click', function () {
    tabs.forEach((tab) => {
      const selected = tab === auditTab;
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.classList.toggle('active', selected);
    });
    panels.forEach((panel) => {
      panel.classList.toggle('hidden', panel !== auditPanel);
    });
  });

  tabs.filter((tab) => tab !== auditTab).forEach((tab) => {
    tab.addEventListener('click', function () {
      auditTab.setAttribute('aria-selected', 'false');
      auditTab.classList.remove('active');
      auditPanel.classList.add('hidden');
    });
  });
})();
