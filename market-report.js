/* BeforeYouSign evidence-led market report. No public API secrets or implicit paid searches. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const es = () => document.documentElement.lang !== 'en';
  const t = (spanish, english) => es() ? spanish : english;
  const euro = (v, digits=0) => new Intl.NumberFormat(es()?'es-ES':'en-IE', {style:'currency',currency:'EUR', maximumFractionDigits:digits}).format(v);
  const plain = (tag, cls, value) => {
    const n = document.createElement(tag);
    if(cls) n.className = cls;
    if(value !== undefined) n.textContent = String(value);
    return n;
  };
  const label = (id, message) => { const target=$(id); if(target)target.textContent=message; };
  let active = null, busy = false;

  function renderBenchmark(result) {
    const box=$('market-benchmark');if(!box)return;
    box.replaceChildren();
    const b=result.market_benchmark;
    if(!b || b.status!=='available'){
      label('market-benchmark-status',t('No tenemos todavía una referencia publicada y verificada para esta zona.',
                                      'No verified published asking-rent benchmark is available for this area yet.'));
      return;
    }
    label('market-benchmark-status',t('Comparación con precios de oferta publicados, no con pisos equivalentes.',
                                    'Compared with published area asking rents, not matched apartments.'));
    const items=[
      [t('Media de oferta de la zona','Area asking-rent headline'),euro(b.eur_sqm,2)+'/m²',t('Idealista · '+b.source_date,'Idealista · '+b.source_date)],
      [t('Este anuncio','This listing'),b.listing_eur_sqm!==null?euro(b.listing_eur_sqm,2)+'/m²':t('Sin datos','Unknown'),t('Alquiler / superficie anunciada','Asking rent / advertised size')],
      [t('Diferencia','Difference'),b.deviation_pct!==null?(b.deviation_pct>0?'+':'')+b.deviation_pct+'%':t('Sin datos','Unknown'),t('No es una tasación','Not a valuation')],
      [t('Alquiler equivalente de la zona','Area-rate equivalent rent'),b.area_implied_monthly_eur!==null?euro(b.area_implied_monthly_eur):t('Sin datos','Unknown'),t('Solo media €/m² × m² anunciados','Area headline €/m² × listed area only')],
    ];
    for(const [heading,value,desc] of items){
      const div=plain('div','report-metric');div.append(plain('small','',heading),plain('strong','',value),plain('small','',desc));box.append(div);
    }
    label('market-area-name',`${b.market_area} · ${b.geography_level==='neighborhood'?t('barrio','neighborhood'):b.geography_level==='district'?t('distrito','district'):t('ciudad','city')}`);
    const a=$('market-source');a.textContent=t('Ver fuente y metodología (octubre de 2026)','View source and methodology (October 2026)');
    if(typeof b.source_url==='string'&&b.source_url.startsWith('https://www.idealista.com/sala-de-prensa/'))a.href=b.source_url;
    let position='';
    if(b.position==='above_area') position=t('El precio anunciado por m² está por encima de la media de oferta de esta zona.','The advertised €/m² is higher than this area’s asking-rent headline.');
    else if(b.position==='below_area') position=t('El precio anunciado por m² está por debajo de la media de oferta de esta zona.','The advertised €/m² is lower than this area’s asking-rent headline.');
    else if(b.position==='near_area') position=t('El precio por m² está cerca de la media de oferta de esta zona.','The advertised €/m² is near this area’s asking-rent headline.');
    else position=t('Necesitamos precio y superficie para comparar.','Rent and area are needed to compare.');
    label('market-benchmark-verdict',position+' '+t('Esta comparación no ajusta tamaño, reforma ni características.','This does not adjust for renovations, apartment type, or condition.'));
  }

  function showComparison(data) {
    const target=$('market-comparable-results');if(!target)return;
    target.replaceChildren();
    const c=data.comparison;
    if(!c) return;
    const count=c.eligible_count||0;
    const countText=plain('p','report-soft',t(`De los ${c.returned_count||0} anuncios consultados, ${count} cumplen los filtros de superficie, distancia y tipo.`,
                                          `${count} of ${c.returned_count||0} returned rentals match the area, size, and type filters.`));
    target.append(countText);
    if(c.median_eur_sqm!==undefined){
      const box=plain('div','report-grid');
      const entries=[
        [t('Mediana de comparables','Comparable median'),euro(c.median_eur_sqm,2)+'/m²'],
        [t('Rango intercuartílico','Middle 50% of asking rents'),`${euro(c.range_eur_sqm[0],2)}–${euro(c.range_eur_sqm[1],2)}/m²`],
        [t('Alquiler equivalente','Median for this size'),euro(c.median_equivalent_rent_eur)],
        [t('Diferencia de este anuncio','Listing vs comparables'),(c.difference_pct>0?'+':'')+c.difference_pct+'%'],
      ];
      for(const [name,value] of entries){const el=plain('div','report-metric');el.append(plain('small','',name),plain('strong','',value));box.append(el)}
      target.append(box);
    }
    let signal;
    if(c.status!=='available')signal=t('Hay muy pocos anuncios adecuados para emitir un veredicto de precio.',
                                       'Too few suitable properties to issue a directional price verdict.');
    else if(c.position==='above_comparables')signal=t('Este anuncio supera la mediana de anuncios similares. No significa necesariamente que sea caro: hay que valorar estado y características.',
                                                        'This listing is above comparable asking rents. Condition and amenities may explain a premium.');
    else if(c.position==='below_comparables')signal=t('Este anuncio está por debajo de la mediana de anuncios similares. Comprueba las condiciones y posibles inconvenientes.',
                                                        'This listing is below comparable asking rents. Check conditions and trade-offs.');
    else signal=t('Este anuncio se sitúa cerca de la mediana de anuncios similares.',
                  'This listing is near comparable asking rents.');
    target.append(plain('p','report-detail-notice',signal));
    const list=plain('ol','market-comparable-list');
    for(const item of (c.comparable_listings||[]).slice(0,12)){
      const li=plain('li','market-comparable-row');
      const a=plain('a','',`#${item.listing_id}`);a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';
      li.append(a,plain('span','',euro(item.rent_eur)+t('/mes','/month')+' · '+item.area_sqm+' m²'),plain('span','',euro(item.eur_sqm,2)+'/m²'),plain('small','',`${item.distance_m} m ${t('en línea recta','straight-line')}`));list.append(li);
    }
    if(list.children.length){target.append(plain('h4','',t('Anuncios utilizados','Listings used')),list);}
    target.append(plain('p','report-soft',t('Son precios anunciados. La distancia parte de un pin aproximado; no son precios de contrato ni se han ajustado las reformas.',
                                              'These are asking prices, not contracted rents. Distances are approximate; renovation quality is not adjusted for.')));
  }

  async function searchComparables() {
    if(!active||busy)return;
    const checkbox=$('market-opt-in');
    if(!checkbox?.checked){label('market-comparables-state',t('Marca la casilla para aceptar que la consulta puede usar un crédito del proveedor.',
                                                              'Check the box to accept that this search may consume a provider credit.'));return;}
    busy=true;const button=$('market-search');if(button)button.disabled=true;
    label('market-comparables-state',t('Consultando la caché y la disponibilidad del buscador…','Checking search cache and provider availability…'));
    try{
      const response=await fetch(String(window.BYS_API_BASE||'').replace(/\/$/,'')+'/api/market/comparables',{
        method:'POST',headers:{'Content-Type':'application/json','X-BYS-Pilot-Code':$('pilot-code')?.value.trim()||''},
        body:JSON.stringify({url:active.source_url,approve_provider_search:true})
      });
      const data=await response.json();
      if(!response.ok)throw Error(data.detail||'Market request failed');
      if(data.comparison){showComparison(data);label('market-comparables-state',data.status==='cached'?t('Resultados guardados en caché; sin nueva consulta de pago.',
            'Shared cached results; no new paid request.') :t('Datos de anuncios obtenidos.','Rental listings retrieved.'));
      }else{
        const messages={
          not_enabled:t('Las consultas de pago siguen desactivadas mientras verificamos el coste y los derechos de uso. No se ha gastado ningún crédito.',
                        'Paid searches remain disabled while pricing and usage rights are checked. No credit was spent.'),
          missing_location:t('La ficha importada no incluye un identificador de zona válido para buscar otros anuncios.',
                             'This cached listing has no search-area ID for comparables.'),
          unavailable:t('No se puede consultar la caché en este momento. No se ha hecho ninguna búsqueda de pago.',
                         'The comparison cache is unavailable. No paid search was made.'),
        };
        label('market-comparables-state',messages[data.status]||data.message||t('No se han podido obtener comparables.','No comparables were available.'));
      }
    }catch(_){label('market-comparables-state',t('No se pudo consultar el informe. No intentes repetir solicitudes de pago continuamente.',
                                                  'The request failed. Please avoid repeated paid attempts.'));}
    finally{busy=false;if(button)button.disabled=false;}
  }

  function prepare(result){
    active=result;
    const section=$('market-review');if(!section)return;
    section.hidden=false;
    const child=$('market-comparable-results');if(child)child.replaceChildren();
    const checkbox=$('market-opt-in');if(checkbox)checkbox.checked=false;
    label('market-comparables-state',t('Los comparables de anuncios requieren una consulta adicional al proveedor. No se hace automáticamente.',
                                      'Listing-level comparables require an additional provider search. Nothing is requested automatically.'));
    renderBenchmark(result);
    const button=$('market-search');if(button)button.onclick=searchComparables;
  }
  document.addEventListener('bys:listing-imported',event=>prepare(event.detail||{}));
  document.addEventListener('bys:listing-reset',()=>{active=null;const s=$('market-review');if(s)s.hidden=true;});
  document.addEventListener('bys:language-changed',()=>{if(active)renderBenchmark(active);});
})();