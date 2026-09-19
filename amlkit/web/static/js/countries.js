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
 * Initialize country dropdown component on an input element
 * Replaces a text input with a searchable dropdown that stores ISO alpha-2 codes
 * @param {HTMLInputElement} input - The input element to enhance
 */
function initCountryDropdown(input) {
  if (!input || input.dataset.countryDropdown === 'initialized') return;
  input.dataset.countryDropdown = 'initialized';

  // Create wrapper
  var wrapper = document.createElement('div');
  wrapper.className = 'country-dropdown-wrapper';
  wrapper.style.position = 'relative';
  wrapper.style.display = 'inline-block';
  wrapper.style.width = '100%';

  // Create display input (what user sees/types)
  var display = document.createElement('input');
  display.type = 'text';
  display.placeholder = input.placeholder || 'Type to search countries...';
  display.autocomplete = 'off';
  display.className = input.className;
  display.setAttribute('aria-label', input.getAttribute('aria-label') || 'Search countries');
  display.setAttribute('aria-autocomplete', 'list');
  display.setAttribute('aria-controls', 'country-dropdown-list');

  // Hidden input stores the ISO code (submitted with form)
  var hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.name = input.name;
  hidden.value = input.value || '';

  // Dropdown list
  var dropdown = document.createElement('div');
  dropdown.id = 'country-dropdown-list';
  dropdown.className = 'country-dropdown-list';
  dropdown.setAttribute('role', 'listbox');
  dropdown.style.display = 'none';
  dropdown.style.position = 'absolute';
  dropdown.style.top = '100%';
  dropdown.style.left = '0';
  dropdown.style.right = '0';
  dropdown.style.maxHeight = '200px';
  dropdown.style.overflowY = 'auto';
  dropdown.style.background = '#fff';
  dropdown.style.border = '1px solid #d1d5db';
  dropdown.style.borderRadius = '4px';
  dropdown.style.marginTop = '2px';
  dropdown.style.zIndex = '1000';
  dropdown.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';

  // Set initial display value from code
  if (hidden.value) {
    var country = window.COUNTRIES.find(function(c) { return c.code === hidden.value.toUpperCase(); });
    if (country) display.value = country.name + ' (' + country.code + ')';
  }

  // Filter and render dropdown
  function renderDropdown(query) {
    var q = (query || '').toLowerCase();
    var filtered = q ? window.COUNTRIES.filter(function(c) {
      return c.name.toLowerCase().indexOf(q) !== -1 || c.code.toLowerCase().indexOf(q) !== -1;
    }) : window.COUNTRIES;

    dropdown.innerHTML = '';
    if (filtered.length === 0) {
      dropdown.innerHTML = '<div style="padding:8px; color:#6b7280;">No matches</div>';
    } else {
      filtered.slice(0, 50).forEach(function(country) {
        var option = document.createElement('div');
        option.className = 'country-option';
        option.textContent = country.name + ' (' + country.code + ')';
        option.dataset.code = country.code;
        option.setAttribute('role', 'option');
        option.style.padding = '8px 12px';
        option.style.cursor = 'pointer';
        option.style.borderBottom = '1px solid #f3f4f6';

        option.addEventListener('mousedown', function(e) {
          e.preventDefault(); // Prevent input blur
          hidden.value = country.code;
          display.value = country.name + ' (' + country.code + ')';
          dropdown.style.display = 'none';
        });

        option.addEventListener('mouseenter', function() {
          option.style.background = '#f3f4f6';
        });

        option.addEventListener('mouseleave', function() {
          option.style.background = '#fff';
        });

        dropdown.appendChild(option);
      });
    }

    dropdown.style.display = 'block';
  }

  // Event handlers
  display.addEventListener('focus', function() {
    renderDropdown(display.value);
  });

  display.addEventListener('input', function() {
    renderDropdown(display.value);
  });

  display.addEventListener('blur', function() {
    // Delay to allow click on option
    setTimeout(function() {
      dropdown.style.display = 'none';
    }, 200);
  });

  display.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      dropdown.style.display = 'none';
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      var firstOption = dropdown.querySelector('.country-option');
      if (firstOption) firstOption.focus();
    }
  });

  // Build DOM
  input.parentNode.insertBefore(wrapper, input);
  wrapper.appendChild(display);
  wrapper.appendChild(hidden);
  wrapper.appendChild(dropdown);
  input.remove();
}

// Auto-initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-country-dropdown]').forEach(function(input) {
    initCountryDropdown(input);
  });
});
