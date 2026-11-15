/* One automatic property-level photo summary from our hosted SmolVLM2 service.
 * Runs after successful listing import; does not download a model to the browser.
 * No OpenData requests and no hidden fallback to the paid OpenAI API.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const api = () => String(window.BYS_API_BASE || '').replace(/\/$/, '');
  const es = () => document.documentElement.lang !== 'en';
  const word = (spanish, english) => es() ? spanish : english;
  let active = null;
  let report = null;
  let runId = 0;
  let refresh = null;
  const el = (tag, content, className) => {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (content !== undefined) n.textContent = String(content);
    return n;
  };
  const message = s => { const element = $('hosted-vision-status'); if (element) element.textContent = s; };

  function display(summary) {
    const target = $('hosted-vision-results');
    if (!target) return;
    target.replaceChildren();
    const locale = es() ? 'es' : 'en';
    const complete = summary.status === 'completed';
    const count = Number(summary.photos_analyzed) || 0;
    const total = Number(summary.photos_available) || 0;
    message(complete
      ? word(`Análisis completado: ${count} fotos disponibles revisadas.`, `Completed: all ${count} available listing photos reviewed.`)
      : word(`Análisis parcial: revisadas ${count} de ${total} fotos disponibles.`, `Partial analysis: ${count} of ${total} available photos reviewed.`));
    target.append(el('h4', word('Resumen general del inmueble','Overall property photo summary')));
    target.append(el('p', summary['summary_'+locale] || summary.summary_en || '', 'report-ai-summary'));
    for (const [key, headingEs, headingEn] of [
      ['visible_strengths','Aspectos visibles positivos','Visible strengths'],
      ['visible_concerns','Aspectos que conviene revisar','Potential visible concerns'],
      ['landlord_questions','Preguntas para el propietario','Questions for the landlord'],
    ]) {
      const entries = summary[key+'_'+locale] || summary[key+'_en'] || [];
      if (!Array.isArray(entries) || !entries.length) continue;
      const section = el('section', undefined, 'report-insight');
      section.append(el('h4', word(headingEs, headingEn)));
      const list = el('ul');
      for (const item of entries.slice(0, 5)) {
        if (typeof item === 'string' && item.trim()) list.append(el('li',item));
      }
      section.append(list);target.append(section);
    }
    target.append(el('p', word(
      'Solo se describe lo que puede observarse en las fotografías. No se han comprobado defectos ocultos, humedades internas, seguridad estructural ni cumplimiento normativo.',
      'Only visible evidence in the photographs is described. Hidden defects, internal moisture, structural safety and compliance have not been verified.'), 'report-soft'));
  }

  const stop = () => {runId++;if(refresh){clearTimeout(refresh);refresh=null;}active=null;report=null;};
  async function fetchStatus(url, method, seq) {
    const opts = {method, headers:{'X-BYS-Pilot-Code': String($('pilot-code')?.value || '').trim()},cache:'no-store'};
    let endpoint = api() + '/api/listings/visual-summary';
    if (method === 'POST') {
      opts.headers['Content-Type']='application/json';
      opts.body=JSON.stringify({url});
    } else {
      endpoint += '?url='+encodeURIComponent(url);
    }
    const c=new AbortController();opts.signal=c.signal;
    const timeout=setTimeout(()=>c.abort(),22000);
    try {
      const response=await fetch(endpoint,opts);
      const data=await response.json();
      if (!response.ok) throw new Error('HTTP '+response.status);
      if (seq!==runId) return null;
      return data;
    } finally {clearTimeout(timeout);}
  }

  function showStatus(data) {
    switch(data.status){
      case 'unconfigured':
        message(word('El análisis automático aún no está activo: falta conectar el servidor del modelo SmolVLM2.',
                     'Automatic analysis is not active yet: the hosted SmolVLM2 model server must be connected.'));
        break;
      case 'daily_limit':
        message(word('Se ha alcanzado el límite diario de análisis visual.', 'Today’s visual-analysis budget has been reached.'));
        break;
      case 'failed':
        message(word('No se pudo completar el análisis visual. No se han inventado conclusiones.',
                     'The visual analysis did not finish. No findings were invented.'));
        break;
      case 'unavailable':
        message(word('No hay fotos utilizables o no está disponible el servicio de análisis.',
                     'There are no usable photos or the analysis service is unavailable.'));
        break;
      default:
        message(word('Preparando el resumen global de las fotos…','Preparing the overall photo summary…'));
    }
  }

  async function poll(seq, attempts) {
    if (!active || seq!==runId) return;
    try {
      const data=await fetchStatus(active.source_url, 'GET', seq);
      if(!data || seq!==runId) return;
      if(['completed','partial'].includes(data.status)){
        report=data;display(data);return;
      }
      if(!['queued','processing','not_started'].includes(data.status)){
        showStatus(data);return;
      }
      const n=Number(data.photos_available)||active.photoCount;
      message(word(`SmolVLM2 está analizando las ${n} fotos disponibles en el servidor…`,
                   `SmolVLM2 is reviewing all ${n} available photos on the server…`));
    } catch (_) {
      message(word('No se ha podido consultar el avance; volveremos a comprobarlo.',
                   'Could not check the progress; retrying status soon.'));
    }
    if(attempts>=210){
      message(word('El análisis está tardando más de lo esperado. Puedes volver más tarde: el resultado se guarda cuando termina.',
                   'Analysis is taking longer than expected. Return later; the result is cached when complete.'));
      return;
    }
    refresh=setTimeout(()=>poll(seq,attempts+1),8000);
  }

  async function begin(listing) {
    stop();
    if(!listing || listing.status!=='imported' || !listing.source_url) return;
    active={source_url:listing.source_url,photoCount:Array.isArray(listing.photo_urls)?listing.photo_urls.length:0};
    const seq=runId;
    const root=$('hosted-vision-results');if(root)root.replaceChildren();
    if(!active.photoCount){
      message(word('El proveedor no ha proporcionado fotos para el análisis visual.',
                   'The listing provider did not provide photos for visual analysis.'));
      return;
    }
    message(word(`Análisis automático solicitado para ${active.photoCount} fotos disponibles…`,
                 `Automatic review requested for ${active.photoCount} available photos…`));
    try {
      const started=await fetchStatus(active.source_url,'POST',seq);
      if(!started || seq!==runId) return;
      if(['completed','partial'].includes(started.status)){
        report=started;display(started);return;
      }
      if(!['queued','processing','not_started'].includes(started.status)){
        showStatus(started);return;
      }
      await poll(seq,0);
    } catch (_) {
      if(seq===runId)message(word('No se pudo iniciar el análisis en el servidor. No se han generado resultados ficticios.',
                                  'Could not start server-side analysis. No findings were invented.'));
    }
  }

  document.addEventListener('bys:listing-imported',e=>begin(e.detail||{}));
  document.addEventListener('bys:listing-reset',stop);
  document.addEventListener('bys:language-change',()=>{if(report)display(report);});
})();