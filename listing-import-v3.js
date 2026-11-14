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

  function locationFromText(text) {
    const lines = String(text || '').replace(/\u00a0/g, ' ').split(/[\r\n]+/).map(s => s.trim()).filter(Boolean);
    for (const line of lines) {
      const labeled = /^(?:ubicaci[oó]n|direcci[oó]n|localizaci[oó]n|location|address|barrio|zona)\s*[:\-]\s*([^.;]{4,90})/i.exec(line);
      if (labeled && labeled[1].trim().length >= 4) return labeled[1].trim().slice(0,90);
      const street = /\b((?:calle|carrer|avenida|avda\.?|plaza|paseo|ronda|travessera)\s+(?:de\s+|del\s+|la\s+|las\s+|los\s+)?[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .'-]{2,70})/i.exec(line);
      if (street) return street[1].trim().slice(0,90);
    }
    const district = /(?:barrio de|zona de|situad[oa] en)\s+(Malasaña|Chamberí|Lavapiés|La Latina|Salamanca|Retiro|Arganzuela|Tetuán|Moncloa|Gràcia|Eixample|Sants|Poble Sec)\b/i.exec(text);
    if (district) return district[1];
    return '';
  }
  let tesseractPromise = null;
  async function getOCR() {
    if (window.Tesseract && window.Tesseract.recognize) return window.Tesseract;
    if (!tesseractPromise) {
      tesseractPromise = new Promise((resolve, reject) => {
        const loader = document.createElement('script');
        loader.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js';
        loader.async = true;
        loader.onload = () => window.Tesseract && window.Tesseract.recognize ? resolve(window.Tesseract) : reject(new Error('OCR library did not load.'));
        loader.onerror = () => reject(new Error('Could not load the free screenshot reader. Check your internet connection or paste listing text.'));
        document.head.appendChild(loader);
      });
    }
    return tesseractPromise;
  }
  async function textFromScreenshots(images) {
    if (!images.length) return '';
    if (images.length > 3) throw new Error('Please upload up to three screenshots at a time.');
    for (const file of images) {
      if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 12_000_000) {
        throw new Error('Use PNG, JPEG or WebP screenshots, each under 12 MB.');
      }
    }
    const tesseract = await getOCR();
    const parts = [];
    for (let i = 0; i < images.length; i++) {
      setMessage('Reading screenshot ' + (i+1) + ' of ' + images.length + ' locally on your device…');
      const result = await tesseract.recognize(images[i], 'spa+eng');
      const recognized = String(result?.data?.text || '').trim();
      if (recognized) parts.push(recognized);
    }
    if (!parts.length) throw new Error('No readable listing text found in these screenshots. Try clearer screenshots.');
    return parts.join('\n');
  }
  function unlockNeighborhood(sourceText) {
    const section = $('neighborhood');
    if (!section) return;
    section.hidden = false;
    const location = locationFromText(sourceText);
    const input = $('map-location');
    const status = $('map-status');
    if (input && location) {
      input.value = location;
      status.textContent = 'Possible location mentioned in the supplied listing. Confirm it before exploring nearby places.';
    } else if (status) {
      status.textContent = 'Location not available from the link alone. Add a screenshot showing its area, or enter its neighborhood here.';
    }
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
  async function tryImportFromProvider(link) {
    if (!apiBase) return null;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 14500);
    try {
      const response = await fetch(apiBase + '/api/listings/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: link.url }),
        signal: controller.signal,
      });
      if (!response.ok) return null;
      const result = await response.json();
      if (!result || result.status !== 'imported' || !result.fields) return null;
      if (result.listing_id !== link.id || result.source_url !== link.url) return null;
      return result;
    } catch (_) {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }
  function showProviderImport(result) {
    const fields = result.fields;
    const count = showFields(fields, 'third-party advertised property data');
    const summary = $('import-summary');
    summary.replaceChildren();
    summary.hidden = false;
    const title = document.createElement('strong');
    title.textContent = 'Property summary';
    summary.append(title);
    const rent = fields.monthly_rent_eur?.value;
    const area = fields.area_sqm?.value;
    if (typeof rent === 'number' && rent > 0 && typeof area === 'number' && area > 0) {
      const line = document.createElement('p');
      line.textContent = 'Asking: ' + new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(rent)
        + '/month · ' + area + ' m² · '
        + new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(rent / area) + '/m²/month.';
      summary.append(line);
    }
    const caveat = document.createElement('p');
    caveat.textContent = 'Details are advertised by a third-party data service, not independently verified. No local rental-price verdict is available without comparable evidence.';
    summary.append(caveat);
    $('import-fallback').hidden = true;
    const location = fields.city_or_area?.value;
    unlockNeighborhood(typeof location === 'string' && location ? 'Location: ' + location : '');
    setMessage('Imported ' + count + ' advertised listing facts. Confirm the details with the advertiser before relying on them.', 'success');
  }
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
    catch (error) { setMessage(error.message, 'error'); return; }
    $('import-property-id').textContent = 'Idealista listing #' + identity.id;
    const summary = $('import-summary');
    summary.replaceChildren();
    summary.hidden = true;
    $('import-evidence').replaceChildren();
    const fallback = $('import-fallback');
    fallback.hidden = true;
    const button = $('import-form').querySelector('[type="submit"]');
    button.disabled = true;
    setMessage('Checking whether verified listing-data access is available…');
    const imported = await tryImportFromProvider(identity);
    button.disabled = false;
    if (imported) {
      showProviderImport(imported);
      return;
    }
    fallback.hidden = false;
    unlockNeighborhood('');
    const userText = trimText($('import-text').value, 40000);
    const screenshots = [...($('import-images')?.files || [])];
    if (!userText && !screenshots.length) {
      setMessage('Listing link saved. To build a reliable property report, add screenshots of the listing below; we cannot retrieve Idealista listing details from its link alone yet.', 'warning');
      const instruction = document.createElement('div');
      instruction.className = 'import-fact';
      instruction.textContent = 'Next: attach screenshots showing the listing price, size, features and location. They can be read locally on your device without an AI account.';
      $('import-evidence').append(instruction);
      return;
    }
    button.disabled = true;
    try {
      let combined = userText;
      if (screenshots.length) {
        const recognized = await textFromScreenshots(screenshots);
        combined = [userText,recognized].filter(Boolean).join('\n');
      }
      combined = trimText(combined,40000);
      setMessage('Extracting advertised property facts…');
      const {fields,source} = await getParsedData(identity,combined);
      const sourceLabel = screenshots.length ? 'uploaded screenshot / listing material' : source;
      const found = showFields(fields,sourceLabel);
      unlockNeighborhood(combined);
      summary.hidden = false;
      const title = document.createElement('strong');
      title.textContent = 'Rental snapshot';
      summary.append(title);
      const rent = fields.monthly_rent_eur?.value;
      const area = fields.area_sqm?.value;
      const validRent = typeof rent === 'number' && Number.isFinite(rent) && rent > 0;
      const validArea = typeof area === 'number' && Number.isFinite(area) && area > 0;
      const line = document.createElement('p');
      if (validRent && validArea) {
        line.textContent = 'Asking price: ' + new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(rent / area) + '/m² per month.';
        summary.append(line);
        const caveat = document.createElement('p');
        caveat.textContent = 'Calculated from the supplied listing content, not independently verified. Neighborhood rent comparisons require genuine comparable listings.';
        summary.append(caveat);
        setMessage('Found ' + found + ' advertised details. Your property snapshot is ready, with evidence and missing information flagged.', 'success');
      } else {
        line.textContent = 'An asking €/m² figure needs both monthly rent and floor area from the listing.';
        summary.append(line);
        setMessage('Extracted ' + found + ' details. Some key listing facts remain unknown. Add clearer screenshots if needed.', 'warning');
      }
    } catch (error) {
      setMessage(error.message || 'Could not read these screenshots. Try a clearer image or paste the listing description.', 'error');
    } finally {
      button.disabled = false;
    }
  });
  $('import-demo').addEventListener('click', () => {
    $('import-fallback').hidden = false;
    $('import-url').value = 'https://www.idealista.com/inmueble/113074128/';
    $('import-text').value = 'Fictional example (not details of this listing): Piso de 75 m², 2 habitaciones, 1 baño, planta 3, con ascensor. 1.500 €/mes.';
    setMessage('Fictional example loaded. Click Analyze listing to see how field extraction works.');
  });
})();