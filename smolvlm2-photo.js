/* Opt-in, on-device photo analysis. No cloud AI key, no automatic model download. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const apiBase = () => String(window.BYS_API_BASE || '').replace(/\/$/, '');
  let active = null;
  let worker = null;
  let taskId = 0;
  let sessionId = 0;
  let pending = null;
  let busy = false;

  const lang = () => document.documentElement.lang === 'en' ? 'en' : 'es';
  const phrase = (es, en) => lang() === 'es' ? es : en;
  const announce = message => { const e = $('smolvlm-status'); if (e) e.textContent = message; };
  const make = (tag, className, text) => {
    const n = document.createElement(tag);if (className) n.className = className;
    if (text !== undefined) n.textContent = String(text);
    return n;
  };

  function shutdown() {
    sessionId++;
    if (pending) {pending.reject(new Error('CANCELLED'));pending=null;}
    if (worker) {worker.terminate();worker=null;}
    busy=false;
    const button=$('smolvlm-run');if(button)button.disabled=false;
  }

  function onWorker(event) {
    const data=event.data||{};
    if (data.status === 'progress') {
      const percent=Math.round(data.progress||0);
      announce(phrase(`Descargando modelo en tu equipo: ${data.file || 'pesos'} (${percent} %)…`,
                      `Downloading the model to your device: ${data.file || 'weights'} (${percent}%)…`));
    } else if (data.status==='loading') {
      announce(phrase('Preparando SmolVLM2-500M en tu navegador. La primera descarga puede ser grande…',
                      'Preparing SmolVLM2-500M in your browser. The first download can be large…'));
    } else if (data.status==='ready') {
      announce(phrase('Modelo cargado. Analizando las fotos localmente…', 'Model loaded. Analyzing photos locally…'));
    } else if (data.status==='analyzing') {
      announce(phrase('Analizando detalles visibles de la foto…', 'Examining visible details in the photo…'));
    } else if ((data.status==='result'||data.status==='error') && pending && pending.requestId===data.requestId) {
      const callbacks=pending;pending=null;
      if(data.status==='result')callbacks.resolve(data.description);
      else callbacks.reject(new Error(data.code||'INFERENCE_FAILED'));
    }
  }

  async function startWorker() {
    if (worker) return worker;
    const instance=new Worker('smolvlm2-worker.js', { type: 'module' });
    instance.addEventListener('message', onWorker);
    instance.addEventListener('error', () => {
      if(pending){const p=pending;pending=null;p.reject(new Error('MODEL_DOWNLOAD_FAILED'));}
      announce(phrase('No se ha podido cargar el motor de IA local. Comprueba la conexión y WebGPU.',
                      'Could not load the local AI engine. Check network access and WebGPU.'));
    });
    worker=instance;
    return instance;
  }

  function inference(buffer, language) {
    if (!worker) return Promise.reject(new Error('INFERENCE_FAILED'));
    const requestId = ++taskId;
    return new Promise((resolve, reject) => {
      pending = { requestId, resolve, reject };
      worker.postMessage({ type:'analyze', buffer, language, requestId }, [buffer]);
    });
  }

  async function obtainPhoto(index) {
    if (!active) throw new Error('MISSING_LISTING');
    const u = new URL(apiBase() + '/api/listings/photo-pixels');
    u.searchParams.set('listing_id', String(active.listingId));
    u.searchParams.set('index', String(index));
    const response = await fetch(u.toString(), {
      headers: { 'X-BYS-Pilot-Code': String($('pilot-code')?.value || '').trim() },
      cache: 'no-store',
    });
    if (!response.ok) throw new Error('PHOTO_FETCH_FAILED');
    if (!(response.headers.get('Content-Type')||'').startsWith('image/jpeg')) throw new Error('PHOTO_FETCH_FAILED');
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength<1000||bytes.byteLength>2_000_000)throw new Error('PHOTO_FETCH_FAILED');
    return bytes;
  }

  async function getUploadedPhotos() {
    const files=[...($('smolvlm-local-photos')?.files||[])].slice(0,3);
    const data=[];
    for (const file of files) {
      if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>12_000_000)continue;
      // Browsers decode user photos, then encode a bounded JPEG entirely locally.
      const bitmap=await createImageBitmap(file);
      try {
        const scale=Math.min(1,768/Math.max(bitmap.width,bitmap.height));
        const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
        canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);
        const blob=await new Promise(ok=>canvas.toBlob(ok,'image/jpeg',0.76));
        if (!blob) continue;
        data.push(await blob.arrayBuffer());
      } finally { bitmap.close(); }
    }
    return data;
  }

  function errorMessage(error) {
    const code=String(error?.message||'');
    const explanations={
      WEBGPU_UNAVAILABLE:phrase('Este navegador o dispositivo no ofrece WebGPU. Prueba Chrome o Edge recientes en un ordenador compatible.',
                               'Your device/browser lacks WebGPU. Try recent Chrome or Edge on a compatible computer.'),
      MODEL_DOWNLOAD_FAILED:phrase('No se pudo descargar el modelo. Comprueba la conexión, el espacio disponible y el acceso a Hugging Face.',
                                   'Could not download the model. Check connection, available space and access to Hugging Face.'),
      OUT_OF_MEMORY:phrase('Memoria gráfica insuficiente. Cierra otras pestañas y vuelve a intentarlo.',
                           'Not enough GPU memory. Close other tabs and try again.'),
      PHOTO_FETCH_FAILED:phrase('No se han podido recuperar las fotos de Idealista desde el servidor. Puedes subir fotos abajo para analizarlas solo en tu dispositivo.',
                                'Could not load Idealista photos through our server. You can upload photos below for local-only analysis.'),
      INVALID_IMAGE:phrase('La imagen no se pudo procesar.', 'The image could not be processed.'),
    };
    return explanations[code]||phrase('No se pudo completar el análisis en este dispositivo. No se han inventado resultados.',
                                      'Local analysis could not finish on this device. No results were invented.');
  }

  async function run() {
    if(busy)return;
    const files=[...($('smolvlm-local-photos')?.files||[])];
    if(!active&&files.length===0){announce(phrase('Importa una vivienda o selecciona fotos.', 'Import a listing or select photos.'));return;}
    if(!navigator.gpu){announce(errorMessage(new Error('WEBGPU_UNAVAILABLE')));return;}
    busy=true;
    $('smolvlm-run').disabled=true;
    const adapter=await navigator.gpu.requestAdapter().catch(()=>null);
    if(!adapter){busy=false;$('smolvlm-run').disabled=false;announce(errorMessage(new Error('WEBGPU_UNAVAILABLE')));return;}
    const results=$('smolvlm-results');results.replaceChildren();
    const runToken=sessionId;
    try {
      let bytes=[];
      if(files.length) {
        announce(phrase('Preparando fotos seleccionadas en el dispositivo…','Preparing your selected photos locally…'));
        bytes=await getUploadedPhotos();
      } else {
        const count=Math.min(Number(active.photoCount)||0,3);
        for(let i=0;i<count;i++){
          announce(phrase(`Recuperando foto ${i+1} de ${count}…`,`Retrieving photo ${i+1} of ${count}…`));
          try {bytes.push(await obtainPhoto(i));}
          catch(error){ if(bytes.length===0)throw error;break; }
        }
      }
      if(runToken!==sessionId)return;
      if(!bytes.length)throw new Error('PHOTO_FETCH_FAILED');
      await startWorker();
      for(let i=0;i<bytes.length;i++){
        if(runToken!==sessionId)return;
        const output=await inference(bytes[i],lang());
        if(runToken!==sessionId)return;
        const card=make('div','report-insight');
        card.append(make('h4','',phrase(`Foto ${i+1} · Observaciones visibles`,`Photo ${i+1} · Visible observations`)));
        card.append(make('p','',output));
        results.append(card);
      }
      announce(phrase(`Se analizaron ${bytes.length} foto(s) localmente con SmolVLM2-500M. Revisa cada observación en persona.`,
                      `${bytes.length} photo(s) analyzed locally with SmolVLM2-500M. Verify observations in person.`));
    } catch(error){ if(runToken===sessionId)announce(errorMessage(error)); }
    finally{ if(runToken===sessionId){busy=false;$('smolvlm-run').disabled=false;} }
  }

  document.addEventListener('bys:photos-ready', event=>{
    shutdown();
    const result=event.detail||{};
    active = { listingId:result.listing_id, photoCount:Array.isArray(result.photo_urls)?result.photo_urls.length:0 };
    const button=$('smolvlm-run');if(button)button.disabled=false;
    const results=$('smolvlm-results');if(results)results.replaceChildren();
    announce(active.photoCount>0
      ? phrase(`${active.photoCount} fotos de anuncio disponibles. Haz clic para analizarlas en tu dispositivo; no hay cargos de OpenAI.`,
               `${active.photoCount} listing photos available. Click to analyze locally; no OpenAI charge.`)
      : phrase('El proveedor no incluyó fotos compatibles. Puedes seleccionar imágenes abajo para analizarlas localmente.',
               'No compatible listing photos were provided. You can select images below for local analysis.'));
  });
  document.addEventListener('bys:listing-reset',()=>{shutdown();active=null;const results=$('smolvlm-results');if(results)results.replaceChildren();});
  $('smolvlm-run')?.addEventListener('click',run);
})();