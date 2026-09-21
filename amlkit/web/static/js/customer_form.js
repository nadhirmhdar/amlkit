var riskSelect = document.getElementById('risk_level');
if (riskSelect) {
    riskSelect.addEventListener('change', function () {
        var eddFields = document.getElementById('edd_fields');
        if (eddFields) {
            eddFields.style.display = this.value === 'high' ? '' : 'none';
        }
    });
}
