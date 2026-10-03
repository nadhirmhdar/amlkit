/**
 * countries.js - ISO 3166-1 alpha-2 country data and searchable dropdown component
 */

// ISO 3166-1 alpha-2 country codes (195 sovereign states)
window.COUNTRIES = [
  {code: "AD", name: "Andorra"},
  {code: "AE", name: "United Arab Emirates"},
  {code: "AF", name: "Afghanistan"},
  {code: "AG", name: "Antigua and Barbuda"},
  {code: "AL", name: "Albania"},
  {code: "AM", name: "Armenia"},
  {code: "AO", name: "Angola"},
  {code: "AR", name: "Argentina"},
  {code: "AT", name: "Austria"},
  {code: "AU", name: "Australia"},
  {code: "AZ", name: "Azerbaijan"},
  {code: "BA", name: "Bosnia and Herzegovina"},
  {code: "BB", name: "Barbados"},
  {code: "BD", name: "Bangladesh"},
  {code: "BE", name: "Belgium"},
  {code: "BF", name: "Burkina Faso"},
  {code: "BG", name: "Bulgaria"},
  {code: "BH", name: "Bahrain"},
  {code: "BI", name: "Burundi"},
  {code: "BJ", name: "Benin"},
  {code: "BN", name: "Brunei"},
  {code: "BO", name: "Bolivia"},
  {code: "BR", name: "Brazil"},
  {code: "BS", name: "Bahamas"},
  {code: "BT", name: "Bhutan"},
  {code: "BW", name: "Botswana"},
  {code: "BY", name: "Belarus"},
  {code: "BZ", name: "Belize"},
  {code: "CA", name: "Canada"},
  {code: "CD", name: "Democratic Republic of the Congo"},
  {code: "CF", name: "Central African Republic"},
  {code: "CG", name: "Republic of the Congo"},
  {code: "CH", name: "Switzerland"},
  {code: "CI", name: "Côte d'Ivoire"},
  {code: "CL", name: "Chile"},
  {code: "CM", name: "Cameroon"},
  {code: "CN", name: "China"},
  {code: "CO", name: "Colombia"},
  {code: "CR", name: "Costa Rica"},
  {code: "CU", name: "Cuba"},
  {code: "CV", name: "Cape Verde"},
  {code: "CY", name: "Cyprus"},
  {code: "CZ", name: "Czech Republic"},
  {code: "DE", name: "Germany"},
  {code: "DJ", name: "Djibouti"},
  {code: "DK", name: "Denmark"},
  {code: "DM", name: "Dominica"},
  {code: "DO", name: "Dominican Republic"},
  {code: "DZ", name: "Algeria"},
  {code: "EC", name: "Ecuador"},
  {code: "EE", name: "Estonia"},
  {code: "EG", name: "Egypt"},
  {code: "ER", name: "Eritrea"},
  {code: "ES", name: "Spain"},
  {code: "ET", name: "Ethiopia"},
  {code: "FI", name: "Finland"},
  {code: "FJ", name: "Fiji"},
  {code: "FM", name: "Micronesia"},
  {code: "FR", name: "France"},
  {code: "GA", name: "Gabon"},
  {code: "GB", name: "United Kingdom"},
  {code: "GD", name: "Grenada"},
  {code: "GE", name: "Georgia"},
  {code: "GH", name: "Ghana"},
  {code: "GM", name: "Gambia"},
  {code: "GN", name: "Guinea"},
  {code: "GQ", name: "Equatorial Guinea"},
  {code: "GR", name: "Greece"},
  {code: "GT", name: "Guatemala"},
  {code: "GW", name: "Guinea-Bissau"},
  {code: "GY", name: "Guyana"},
  {code: "HN", name: "Honduras"},
  {code: "HR", name: "Croatia"},
  {code: "HT", name: "Haiti"},
  {code: "HU", name: "Hungary"},
  {code: "ID", name: "Indonesia"},
  {code: "IE", name: "Ireland"},
  {code: "IL", name: "Israel"},
  {code: "IN", name: "India"},
  {code: "IQ", name: "Iraq"},
  {code: "IR", name: "Iran"},
  {code: "IS", name: "Iceland"},
  {code: "IT", name: "Italy"},
  {code: "JM", name: "Jamaica"},
  {code: "JO", name: "Jordan"},
  {code: "JP", name: "Japan"},
  {code: "KE", name: "Kenya"},
  {code: "KG", name: "Kyrgyzstan"},
  {code: "KH", name: "Cambodia"},
  {code: "KI", name: "Kiribati"},
  {code: "KM", name: "Comoros"},
  {code: "KN", name: "Saint Kitts and Nevis"},
  {code: "KP", name: "North Korea"},
  {code: "KR", name: "South Korea"},
  {code: "KW", name: "Kuwait"},
  {code: "KZ", name: "Kazakhstan"},
  {code: "LA", name: "Laos"},
  {code: "LB", name: "Lebanon"},
  {code: "LC", name: "Saint Lucia"},
  {code: "LI", name: "Liechtenstein"},
  {code: "LK", name: "Sri Lanka"},
  {code: "LR", name: "Liberia"},
  {code: "LS", name: "Lesotho"},
  {code: "LT", name: "Lithuania"},
  {code: "LU", name: "Luxembourg"},
  {code: "LV", name: "Latvia"},
  {code: "LY", name: "Libya"},
  {code: "MA", name: "Morocco"},
  {code: "MC", name: "Monaco"},
  {code: "MD", name: "Moldova"},
  {code: "ME", name: "Montenegro"},
  {code: "MG", name: "Madagascar"},
  {code: "MH", name: "Marshall Islands"},
  {code: "MK", name: "North Macedonia"},
  {code: "ML", name: "Mali"},
  {code: "MM", name: "Myanmar"},
  {code: "MN", name: "Mongolia"},
  {code: "MR", name: "Mauritania"},
  {code: "MT", name: "Malta"},
  {code: "MU", name: "Mauritius"},
  {code: "MV", name: "Maldives"},
  {code: "MW", name: "Malawi"},
  {code: "MX", name: "Mexico"},
  {code: "MY", name: "Malaysia"},
  {code: "MZ", name: "Mozambique"},
  {code: "NA", name: "Namibia"},
  {code: "NE", name: "Niger"},
  {code: "NG", name: "Nigeria"},
  {code: "NI", name: "Nicaragua"},
  {code: "NL", name: "Netherlands"},
  {code: "NO", name: "Norway"},
  {code: "NP", name: "Nepal"},
  {code: "NR", name: "Nauru"},
  {code: "NZ", name: "New Zealand"},
  {code: "OM", name: "Oman"},
  {code: "PA", name: "Panama"},
  {code: "PE", name: "Peru"},
  {code: "PG", name: "Papua New Guinea"},
  {code: "PH", name: "Philippines"},
  {code: "PK", name: "Pakistan"},
  {code: "PL", name: "Poland"},
  {code: "PT", name: "Portugal"},
  {code: "PW", name: "Palau"},
  {code: "PY", name: "Paraguay"},
  {code: "QA", name: "Qatar"},
  {code: "RO", name: "Romania"},
  {code: "RS", name: "Serbia"},
  {code: "RU", name: "Russia"},
  {code: "RW", name: "Rwanda"},
  {code: "SA", name: "Saudi Arabia"},
  {code: "SB", name: "Solomon Islands"},
  {code: "SC", name: "Seychelles"},
  {code: "SD", name: "Sudan"},
  {code: "SE", name: "Sweden"},
  {code: "SG", name: "Singapore"},
  {code: "SI", name: "Slovenia"},
  {code: "SK", name: "Slovakia"},
  {code: "SL", name: "Sierra Leone"},
  {code: "SM", name: "San Marino"},
  {code: "SN", name: "Senegal"},
  {code: "SO", name: "Somalia"},
  {code: "SR", name: "Suriname"},
  {code: "SS", name: "South Sudan"},
  {code: "ST", name: "São Tomé and Príncipe"},
  {code: "SV", name: "El Salvador"},
  {code: "SY", name: "Syria"},
  {code: "SZ", name: "Eswatini"},
  {code: "TD", name: "Chad"},
  {code: "TG", name: "Togo"},
  {code: "TH", name: "Thailand"},
  {code: "TJ", name: "Tajikistan"},
  {code: "TL", name: "Timor-Leste"},
  {code: "TM", name: "Turkmenistan"},
  {code: "TN", name: "Tunisia"},
  {code: "TO", name: "Tonga"},
  {code: "TR", name: "Turkey"},
  {code: "TT", name: "Trinidad and Tobago"},
  {code: "TV", name: "Tuvalu"},
  {code: "TZ", name: "Tanzania"},
  {code: "UA", name: "Ukraine"},
  {code: "UG", name: "Uganda"},
  {code: "US", name: "United States"},
  {code: "UY", name: "Uruguay"},
  {code: "UZ", name: "Uzbekistan"},
  {code: "VA", name: "Vatican City"},
  {code: "VC", name: "Saint Vincent and the Grenadines"},
  {code: "VE", name: "Venezuela"},
  {code: "VN", name: "Vietnam"},
  {code: "VU", name: "Vanuatu"},
  {code: "WS", name: "Samoa"},
  {code: "YE", name: "Yemen"},
  {code: "ZA", name: "South Africa"},
  {code: "ZM", name: "Zambia"},
  {code: "ZW", name: "Zimbabwe"}
];

/**
 * Initialize country dropdown component on an input element.
 *
 * Replaces a text input with an ARIA 1.2 combobox (editable, list
 * autocomplete) that stores the ISO alpha-2 code in a hidden input:
 *  - role=combobox + aria-expanded/aria-controls/aria-activedescendant on
 *    the visible input; role=listbox/option (ids unique per instance) on
 *    the list, so screen readers announce the highlighted country.
 *  - ArrowDown/ArrowUp move the highlight, Enter picks it, Escape closes.
 *  - On blur, text that resolves to exactly one country snaps to it;
 *    anything else clears the code and shows "Choose a country from the
 *    list" inline, so free text never silently posts an empty value.
 * The original input's id moves to the visible input, so an existing
 * <label for="..."> keeps naming the combobox.
 * @param {HTMLInputElement} input - The input element to enhance
 */
var countryDropdownCount = 0;

function countryLabel(c) { return c.name + ' (' + c.code + ')'; }

function initCountryDropdown(input) {
  if (!input || input.dataset.countryDropdown === 'initialized') return;
  input.dataset.countryDropdown = 'initialized';
  var uid = 'country-cb-' + (++countryDropdownCount);
  var labelEl = input.labels && input.labels.length ? input.labels[0] : null;

  var wrapper = document.createElement('div');
  wrapper.className = 'country-dropdown-wrapper';

  // Visible combobox input (what the user sees/types)
  var display = document.createElement('input');
  display.type = 'text';
  display.id = input.id || (uid + '-input');
  display.placeholder = input.placeholder || 'Type to search countries...';
  display.autocomplete = 'off';
  display.className = input.className;
  if (input.getAttribute('aria-label') || !labelEl) {
    display.setAttribute('aria-label', input.getAttribute('aria-label') || 'Search countries');
  }
  display.setAttribute('role', 'combobox');
  display.setAttribute('aria-autocomplete', 'list');
  display.setAttribute('aria-expanded', 'false');
  display.setAttribute('aria-controls', uid + '-list');

  // Hidden input stores the ISO code (submitted with form)
  var hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.name = input.name;
  hidden.value = input.value || '';

  var dropdown = document.createElement('div');
  dropdown.id = uid + '-list';
  dropdown.className = 'country-dropdown-list';
  dropdown.setAttribute('role', 'listbox');
  if (labelEl) {
    if (!labelEl.id) labelEl.id = uid + '-label';
    dropdown.setAttribute('aria-labelledby', labelEl.id);
  } else {
    dropdown.setAttribute('aria-label', 'Countries');
  }
  dropdown.hidden = true;

  var error = document.createElement('p');
  error.id = uid + '-error';
  error.className = 'field-error';
  error.setAttribute('role', 'alert');
  error.hidden = true;

  var matches = [];
  var active = -1;

  function findByCode(code) {
    code = (code || '').toUpperCase();
    return window.COUNTRIES.find(function(c) { return c.code === code; }) || null;
  }

  function filter(query) {
    var q = (query || '').trim().toLowerCase();
    if (!q) return window.COUNTRIES.slice();
    return window.COUNTRIES.filter(function(c) {
      return c.name.toLowerCase().indexOf(q) !== -1 || c.code.toLowerCase().indexOf(q) !== -1
        || countryLabel(c).toLowerCase() === q;
    });
  }

  // Exact match on name, ISO code or the "Name (CODE)" display form.
  function exactMatch(text) {
    var q = (text || '').trim().toLowerCase();
    if (!q) return null;
    return window.COUNTRIES.find(function(c) {
      return c.name.toLowerCase() === q || c.code.toLowerCase() === q || countryLabel(c).toLowerCase() === q;
    }) || null;
  }

  // True when the visible text is exactly the current selection's label.
  function showingSelection() {
    var current = findByCode(hidden.value);
    return !!current && display.value.trim() === countryLabel(current);
  }

  if (hidden.value) {
    var initial = findByCode(hidden.value);
    if (initial) display.value = countryLabel(initial);
  }

  function isOpen() { return !dropdown.hidden; }

  function setActive(i) {
    var opts = dropdown.querySelectorAll('[role="option"]');
    if (active >= 0 && opts[active]) {
      opts[active].classList.remove('is-active');
      opts[active].setAttribute('aria-selected', 'false');
    }
    active = i;
    if (i >= 0 && opts[i]) {
      opts[i].classList.add('is-active');
      opts[i].setAttribute('aria-selected', 'true');
      display.setAttribute('aria-activedescendant', opts[i].id);
      if (opts[i].scrollIntoView) opts[i].scrollIntoView({ block: 'nearest' });
    } else {
      display.removeAttribute('aria-activedescendant');
    }
  }

  function open(query) {
    matches = filter(query).slice(0, 50);
    dropdown.textContent = '';
    active = -1;
    display.removeAttribute('aria-activedescendant');
    if (matches.length === 0) {
      var none = document.createElement('div');
      none.className = 'country-option country-option--empty';
      none.textContent = 'No matches';
      dropdown.appendChild(none);
    }
    matches.forEach(function(country, i) {
      var option = document.createElement('div');
      option.id = uid + '-opt-' + i;
      option.className = 'country-option';
      option.textContent = countryLabel(country);
      option.dataset.code = country.code;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      option.addEventListener('mousedown', function(e) {
        e.preventDefault(); // keep focus in the input
        choose(country);
      });
      option.addEventListener('mousemove', function() {
        if (active !== i) setActive(i);
      });
      dropdown.appendChild(option);
    });
    dropdown.hidden = false;
    display.setAttribute('aria-expanded', 'true');
  }

  function close() {
    setActive(-1);
    dropdown.hidden = true;
    display.setAttribute('aria-expanded', 'false');
  }

  function showError(on) {
    error.hidden = !on;
    error.textContent = on ? 'Choose a country from the list' : '';
    if (on) {
      display.setAttribute('aria-invalid', 'true');
      display.setAttribute('aria-describedby', error.id);
    } else {
      display.removeAttribute('aria-invalid');
      display.removeAttribute('aria-describedby');
    }
  }

  function choose(country) {
    hidden.value = country.code;
    display.value = countryLabel(country);
    showError(false);
    close();
  }

  // Reconcile the typed text with the hidden code. Returns false when the
  // text could not be resolved to a single country.
  function commit() {
    var text = display.value.trim();
    if (showingSelection()) { showError(false); return true; }
    if (!text) { hidden.value = ''; showError(false); return true; }
    var hit = exactMatch(text);
    if (!hit) {
      var candidates = filter(text);
      if (candidates.length === 1) hit = candidates[0];
    }
    if (hit) { choose(hit); return true; }
    hidden.value = '';
    showError(true);
    return false;
  }

  display.addEventListener('focus', function() {
    open(showingSelection() ? '' : display.value);
  });
  display.addEventListener('input', function() {
    hidden.value = '';
    showError(false);
    open(display.value);
  });
  display.addEventListener('blur', function() {
    close();
    commit();
  });
  display.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen()) open(showingSelection() ? '' : display.value);
      if (!matches.length) return;
      var next = e.key === 'ArrowDown' ? active + 1 : active - 1;
      if (next >= matches.length) next = 0;
      if (next < 0) next = matches.length - 1;
      setActive(next);
    } else if (e.key === 'Enter') {
      if (isOpen() && active >= 0 && matches[active]) {
        e.preventDefault(); // pick the option rather than submit the form
        choose(matches[active]);
      }
    } else if (e.key === 'Escape') {
      if (isOpen()) {
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    }
  });

  // Never post a country the user typed but didn't resolve.
  var form = input.form;
  if (form) {
    form.addEventListener('submit', function(e) {
      if (!commit()) {
        e.preventDefault();
        display.focus();
      }
    });
  }

  input.parentNode.insertBefore(wrapper, input);
  wrapper.appendChild(display);
  wrapper.appendChild(hidden);
  wrapper.appendChild(dropdown);
  wrapper.appendChild(error);
  input.remove();
}

// Auto-initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-country-dropdown]').forEach(function(input) {
    initCountryDropdown(input);
  });
});
