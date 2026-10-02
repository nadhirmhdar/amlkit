// /apply: show the consultant-only field, relax the name field for
// professionals, and drop the firm and job-title fields for a natural person. Progressive enhancement only: the server validates every rule,
// and with this script off the form still works (every field is shown).
(function () {
  "use strict";
  var radios = document.querySelectorAll('input[name="applicant_type"]');
  var consultantBox = document.getElementById("ap-consultant-fields");
  var clientFirms = document.getElementById("ap-client_firms");
  var orgInput = document.getElementById("ap-org_name");
  var orgLabel = document.getElementById("ap-org-label");
  var orgOptional = document.getElementById("ap-org-optional");
  var orgField = document.getElementById("ap-org-field");
  var jobField = document.getElementById("ap-job-field");
  var jobInput = document.getElementById("ap-job_title");
  var legend = document.getElementById("ap-firm-legend");
  if (!radios.length || !orgInput) return;

  function apply() {
    var chosen = document.querySelector('input[name="applicant_type"]:checked');
    var isConsultant = !!chosen && chosen.dataset.consultant === "yes";
    var nameOptional = !!chosen && chosen.dataset.nameOptional === "yes";
    if (consultantBox) consultantBox.hidden = !isConsultant;
    if (clientFirms) clientFirms.required = isConsultant;
    var noFirm = !!chosen && chosen.dataset.noFirm === "yes";
    if (orgField) orgField.hidden = noFirm;
    if (jobField) jobField.hidden = noFirm;
    // Disabled fields are not submitted, so nothing stale is sent for a person.
    orgInput.disabled = noFirm;
    if (jobInput) jobInput.disabled = noFirm;
    if (legend) legend.textContent = noFirm ? "Your activity" : "Your firm";
    orgInput.required = !nameOptional && !noFirm;
    if (orgOptional) orgOptional.hidden = !nameOptional;
    if (orgLabel) {
      orgLabel.textContent = isConsultant ? "Consultancy name"
        : nameOptional ? (chosen.value === "Professional" ? "Practice name" : "Trading name")
        : "Firm name";
    }
  }
  for (var i = 0; i < radios.length; i++) radios[i].addEventListener("change", apply);
  apply();
})();
