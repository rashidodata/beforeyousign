/* BeforeYouSign rental-first intake. No scraping or API keys in the browser. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const allowed = new Set(['idealista.com', 'www.idealista.com', 'idealista.pt', 'www.idealista.pt', 'idealista.it', 'www.idealista.it']);
  const setMessage = (message, kind = 'info') => {
    $('import-status').textContent = message;
    $('import-status').dataset.kind = kind;
  };
  const trimText = (s, max) => String(s || '').slice(0, max).trim();
  function listingUrl(value) {
    const link = new URL(value);
    if (link.protocol !== 'https:' || !allowed.has(link.hostname) || link.username || link.password || link.port) {
      throw new Error('Use a full HTTPS Idealista property listing link.');
    }
    const match = /^\/inmueble\/(\d{5,14})(?:\/|$)/.exec(link.pathname);
    if (!match) throw new Error('This link does not point to an individual Idealista property.');
    return { id: match[1], url: `https://${link.hostname}/inmueble/${match[1]}/` };
  }
  function positiveNumber(s) {
    let text = String(s || '').replace(/\s/g, '');
    if (text.includes(',') && text.includes('.')) {
      text = text.lastIndexOf(',') > text.lastIndexOf('.') ? text.replace(/\./g, '').replace(',', '.') : text.replace(/,/g, '');
    } else if (/^\d{1,3}(?:[.,]\d{3})+$/.test(text)) {
      text = text.replace(/[.,]/g, '');
    } else if (text.includes(',')) {
      text = text.replace(',', '.');
    }
    const n = Number(text);
    return Number.isFinite(n) && n > 0 ? n : null;
  }
  function observed(text, patterns, min, max) {
    for (const pattern of patterns) {
      const m = pattern.exec(text);
      if (!m) continue;
      const n = positiveNumber(m[1]);
      if (n !== null && n >= min && n <= max) return { value: n, evidence: m[0], status: 'observed' };
    }
    return { value: null, evidence: '', status: 'unknown' };
  }
  function extractFromText(raw) {
    const text = raw.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').slice(0, 40000);
    return {
      monthly_rent_eur: observed(text, [/(\d[\d., ]{1,12})\s*€\s*\/\s*(?:mes|month|mês)/i, /(?:alquiler|renta|rent|precio)\s*[:\-]?\s*(\d[\d., ]{1,12})\s*€/i], 100, 100000),
      area_sqm: observed(text, [/(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:m²|m2|m\^2|metros cuadrados)(?!\s*\/)/i], 8, 20000),
      bedrooms: observed(text, [/(\d{1,2})\s*(?:hab\.?|habitaciones?|dormitorios?|bedrooms?)/i], 1, 40),
      bathrooms: observed(text, [/(\d{1,2})\s*(?:baños?|bathrooms?)/i], 1, 40),
      floor: observed(text, [/(?:planta|floor|piso)\s*(\d{1,2})(?:ª|º|a|o)?\b/i, /(\d{1,2})(?:ª|º)\s*planta/i], 0, 99),
    };
  }
  function showFields(fields, sourceLabel) {
    const definitions = [
      ['monthly_rent_eur', 'Monthly rent', '€'], ['area_sqm', 'Floor area', 'm²'],
      ['bedrooms', 'Bedrooms', ''], ['bathrooms', 'Bathrooms', ''], ['floor', 'Floor', '']
    ];
    $('import-evidence').replaceChildren();
    let found = 0;
    for (const [key, name, unit] of definitions) {
      const obj = fields[key] || { value: null };
      const item = document.createElement('div');
      item.className = 'import-fact';
      const title = document.createElement('strong');
      title.textContent = name;
      const value = document.createElement('span');
      value.textContent = obj.value === null || obj.value === undefined ? 'Not found' : `${obj.value}${unit ? ' ' + unit : ''}`;
      const evidence = document.createElement('small');
      evidence.textContent = obj.value === null || obj.value === undefined ? 'Needs confirmation' : `From ${sourceLabel}: “${String(obj.evidence || '').slice(0,85)}”`;
      item.append(title, value, evidence);
      $('import-evidence').append(item);
      if (obj.value !== null && obj.value !== undefined) found++;
    }
    return found;
  }
  const apiBase = trimText(window.BYS_API_BASE || '', 300).replace(/\/$/, '');
  async function getParsedData(link, text) {
    if (apiBase) {
      try {
        const response = await fetch(`${apiBase}/api/listings/parse`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: link.url, listing_text: text })
        });
        if (response.ok) {
          const data = await response.json();
          const rows = data.extraction?.fields || {};
          const fields = {};
          for (const [key, row] of Object.entries(rows)) fields[key] = { value: row.value, evidence: row.evidence, status: row.source === 'not_found' ? 'unknown' : 'observed' };
          return { fields, source: 'provided listing text' };
        }
      } catch (_) { /* Continue with on-device extraction. */ }
    }
    return { fields: extractFromText(text), source: 'provided listing text' };
  }
  $('import-form').addEventListener('submit', async event => {
    event.preventDefault();
    let identity;
    try { identity = listingUrl(trimText($('import-url').value, 2000)); }
    catch (e) { setMessage(e.message, 'error'); return; }
    const text = trimText($('import-text').value, 40000);
    $('import-property-id').textContent = `Idealista listing #${identity.id}`;
    if (!text) {
      $('import-evidence').replaceChildren();
      setMessage('Link recognized. We do not automatically read Idealista without authorized access. For now, paste the property description to extract its details; direct one-link import and screenshot analysis are not yet available.', 'warning');
      $('import-text').focus();
      return;
    }
    setMessage('Extracting listing information…');
    const { fields, source } = await getParsedData(identity, text);
    const count = showFields(fields, source);
    const rent = fields.monthly_rent_eur?.value;
    const area = fields.area_sqm?.value;
    const summary = $('import-summary');
    summary.replaceChildren();
    summary.hidden = false;
    const title = document.createElement('strong');
    title.textContent = 'Rental snapshot';
    summary.append(title);
    const line = document.createElement('p');
    const validRent = typeof rent === 'number' && Number.isFinite(rent) && rent > 0;
    const validArea = typeof area === 'number' && Number.isFinite(area) && area > 0;
    if (validRent && validArea) {
      const pricePerSqm = rent / area;
      line.textContent = new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(pricePerSqm)
        + '/m² per month, calculated from the supplied asking rent and floor area.';
      summary.append(line);
      const caveat = document.createElement('p');
      caveat.textContent = 'This is not a market valuation. A fair-price recommendation requires verified nearby rental comparables.';
      summary.append(caveat);
      setMessage(`Found ${count} advertised fields. Your rental snapshot is ready below; no manual calculator required.`, 'success');
    } else {
      line.textContent = 'A reliable rent-per-m² figure needs both the advertised monthly rent and floor area.';
      summary.append(line);
      setMessage(`Found ${count} advertised fields. Some important details are missing from the supplied description; we will not invent them.`, 'warning');
    }
  });
  $('import-demo').addEventListener('click', () => {
    $('import-url').value = 'https://www.idealista.com/inmueble/113074128/';
    $('import-text').value = 'Fictional example (not details of this listing): Piso de 75 m², 2 habitaciones, 1 baño, planta 3, con ascensor. 1.500 €/mes.';
    setMessage('Fictional example loaded. Click Analyze listing to see how field extraction works.');
  });
})();