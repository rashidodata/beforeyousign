/* BeforeYouSign: link-to-report layer. All figures are traceable to imported facts
 * or explicitly editable examples. No browser access to OpenData/OpenAI keys. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const euro = (n, decimals = 0) => new Intl.NumberFormat('en-IE', {style:'currency',currency:'EUR', maximumFractionDigits:decimals}).format(n);
  const isNum = n => typeof n === 'number' && Number.isFinite(n);
  const value = (fields, key) => fields && fields[key] ? fields[key].value : null;
  const numberValue = (fields, key) => {
    const v = value(fields, key); return isNum(v) ? v : null;
  };
  const node = (tag, className, text) => {
    const el=document.createElement(tag);
    if(className)el.className=className;
    if(text!==undefined)el.textContent=String(text);
    return el;
  };
  const attachText = (target,tag,className,text) => {const x=node(tag,className,text);target.append(x);return x;};
  const clear = el => {if (el) el.replaceChildren();};
  const byId = id => document.getElementById(id);
  const status = (id, text) => {const e=byId(id);if(e)e.textContent=text;};

  function metrics(result) {
    const f=result.fields||{};
    const rent=numberValue(f,'monthly_rent_eur');
    const area=numberValue(f,'area_sqm');
    const target=$('report-metrics');clear(target);
    const records=[
      ['Monthly rent',rent!==null?euro(rent):'Unknown','Advertised, not independently verified'],
      ['Asking €/m²',rent!==null&&area?euro(rent/area,2):'Unknown','Calculated from advertised values'],
      ['Annual rent',rent!==null?euro(12*rent):'Unknown','Excludes utilities and fees'],
      ['Listed area',area!==null?`${area} m²`:'Unknown','Confirm measured usable area'],
    ];
    for(const [k,v,hint] of records){const d=node('div','report-metric');attachText(d,'small','',k);attachText(d,'strong','',v);attachText(d,'small','',hint);target.append(d);}
    const pros=$('report-pros');clear(pros);
    const questions=$('report-concerns');clear(questions);
    const flags=[...(Array.isArray(result.pros)?result.pros:[])].slice(0,5);
    const risks=[...(Array.isArray(result.cons)?result.cons:[])].slice(0,5);
    for(const item of flags)attachText(pros,'li','',item);
    if(!flags.length)attachText(pros,'li','','No listed advantages have been independently verified.');
    for(const item of risks)attachText(questions,'li','',item);
    if(!risks.length)attachText(questions,'li','','Ask about noise, ventilation, service charges and maintenance before signing.');
    if(result.listing_state && result.listing_state!=='active')attachText(questions,'li','','Provider listing status: '+result.listing_state+' — confirm availability.');
    status('report-market-verdict','Market comparison: unavailable until we have at least three recent, similar nearby rental listings. We will not invent an area median or label this home a bargain.');
  }

  function recalcCosts(result) {
    const f=result.fields||{}; const rent=numberValue(f,'monthly_rent_eur');
    const area=numberValue(f,'area_sqm');
    const target=$('report-cost-results');clear(target);
    if(rent===null || rent<=0){target.textContent='Monthly rent was not found, so a meaningful cost calculation cannot be made.';return;}
    const read=(id, limit=100000)=>{const v=Number($(id)?.value||0);return Number.isFinite(v)?Math.min(Math.max(0,v),limit):0;};
    const extras=read('cost-utilities')+read('cost-internet')+read('cost-insurance')+read('cost-other');
    const upfront=read('cost-deposit-months',12)*rent + read('cost-upfront-extra');
    const monthly=rent+extras;
    const cashToStart=rent+upfront;
    const income=read('cost-income',1000000);
    const values=[
      ['Monthly housing budget',euro(monthly),`Rent ${euro(rent)} + editable extras ${euro(extras)}`],
      ['Year-one recurring cost',euro(12*monthly),'Twelve months of rent and editable extras; excludes one-off deposits'],
      ['Move-in cash estimate',euro(cashToStart),'First rent + editable deposit and one-off costs (refundable deposit is not a fee)'],
      ['Household rent burden',income>0?`${Math.round(100*rent/income)}%`:'Add income','Advertised rent ÷ optional monthly take-home income'],
    ];
    for(const [name,amount,desc] of values){const d=node('div','report-metric');attachText(d,'small','',name);attachText(d,'strong','',amount);attachText(d,'small','',desc);target.append(d);}
    status('report-cost-footnote', 'Editable assumptions, not fees confirmed by the landlord. ' + (area&&rent ? `All-in example ${euro(monthly/area,2)}/m²/month. ` : '') + 'Check what bills, deposit, agency costs and insurance are actually required.');
  }

  const categories=[['Supermarkets','Groceries for the week','shopping-basket'],['Local markets','Fresh food and local stalls','store'],['Pharmacies','Everyday health essentials','cross'],['Public transport','Getting around','train'],['Parks','Green space for a break','trees'],['Schools & nurseries','Education nearby','graduation-cap'],['Cafes','Coffee and third places','coffee']];
  function renderGroups(groups, result) {
    const grid=$('report-nearby-groups');clear(grid);
    for(const [cat,description] of categories){
      const card=node('section','report-place-card');attachText(card,'h4','',cat);attachText(card,'p','report-soft',description);
      const arr=Array.isArray(groups[cat])?groups[cat]:[];
      if(!arr.length)attachText(card,'p','report-empty','No named location in this category was returned within 1.2 km.');
      else {
        const list=node('ol','report-places');
        arr.slice(0,3).forEach(place=>{
          const li=node('li');const a=node('a','',place.name);
          if(typeof place.source_url==='string'&&/^https:\/\/www\.openstreetmap\.org\/(?:node|way|relation)\/\d+$/.test(place.source_url)){
            a.href=place.source_url;a.rel='noopener noreferrer';a.target='_blank';
          }
          li.append(a);attachText(li,'span','report-distance',`${Math.round(place.distance_m)} m`);
          list.append(li);
        });card.append(list);
      }grid.append(card);
    }
    const near=groups.Supermarkets||[], trans=groups['Public transport']||[], parks=groups.Parks||[];
    const bits=[];
    if(near.length)bits.push(`${near[0].name} is the closest mapped grocery option, about ${near[0].distance_m} m from the pin`);
    if(trans.length)bits.push(`the closest mapped transit option is ${trans[0].name}, about ${trans[0].distance_m} m away`);
    if(parks.length)bits.push(`${parks[0].name} is the nearest named green space found`);
    status('report-neighborhood-takeaway',bits.length?bits.join('; ')+'. These are straight-line map distances, not confirmed walking routes.':'The mapped area has limited named points of interest in the available source; that does not mean amenities are absent.');
  }

  async function neighborhood(result) {
    const pin=result.map_pin, title=value(result.fields||{},'city_or_area');
    const approx=pin?.approximate!==false;
    status('report-neighborhood-heading', title?`Around ${title}`:'Around this listing');
    status('report-neighborhood-notice',pin?.note||'No usable map coordinates were supplied by the listing provider.');
    clear($('report-nearby-groups'));
    if(!pin || !isNum(pin.latitude) || !isNum(pin.longitude)){
      status('report-neighborhood-state','The listing feed does not supply usable coordinates. Exact nearby distances cannot be calculated from a city name alone.');
      return;
    }
    status('report-neighborhood-state','Finding nearby shops, green space and transit from mapped OpenStreetMap places…');
    try {
      const u=new URL((window.BYS_API_BASE||'').replace(/\/$/,'')+'/api/neighborhood/summary');
      u.searchParams.set('lat',String(pin.latitude));u.searchParams.set('lon',String(pin.longitude));u.searchParams.set('radius_m','1200');
      const response=await fetch(u.toString(),{headers:{'X-BYS-Pilot-Code':$('pilot-code').value.trim()}});
      const data=await response.json();
      if(!response.ok||data.status!=='ok'){
        status('report-neighborhood-state',data.reason||'Nearby places are temporarily unavailable. No names or distances have been invented.');return;
      }
      renderGroups(data.groups||{},result);
      status('report-neighborhood-state',`${approx?'Approximate listing location':'Advertised map pin'} · straight-line distances · OpenStreetMap contributors`);
    } catch (_) {status('report-neighborhood-state','We could not load nearby places. Try again shortly. No distances have been guessed.');}
  }

  function renderAI(data) {
    const root=$('report-ai-findings');clear(root);
    attachText(root,'p','report-ai-summary',data.summary||'No photo summary was supplied.');
    for(const [title,key] of [['Visible positives','visible_strengths'],['Things to check','visible_concerns']]){
      const findings=Array.isArray(data[key])?data[key]:[];
      if(!findings.length)continue;
      const sec=node('section','report-insight');attachText(sec,'h4','',title);
      const list=node('ul');findings.slice(0,6).forEach(f=>{
        const t=typeof f==='string'?f:String(f.finding||'');
        if(t)attachText(list,'li','',t+(f.evidence_photo?' — photo '+f.evidence_photo:''));
      });sec.append(list);root.append(sec);
    }
    const questions=Array.isArray(data.landlord_questions)?data.landlord_questions:[];
    if(questions.length){const sec=node('section','report-insight');attachText(sec,'h4','','Questions to ask the landlord');const ul=node('ul');questions.slice(0,6).forEach(q=>attachText(ul,'li','',q));sec.append(ul);root.append(sec);}
    const unknown=Array.isArray(data.not_verifiable_from_photos)?data.not_verifiable_from_photos:[];
    if(unknown.length){attachText(root,'p','report-soft','Cannot be verified from photos: '+unknown.slice(0,7).join('; ')+'.');}
    status('report-ai-state',`AI reviewed ${data.images_analyzed||'?'} advertised image(s). Visual observations are not a structural survey or proof of property condition.`);
  }

  async function photos(result) {
    const urls=Array.isArray(result.photo_urls)?result.photo_urls:[];
    const strip=$('report-photo-strip');clear(strip);
    for(const u of urls.slice(0,5)){
      if(typeof u!=='string'||!/^https:\/\/(?:[a-z0-9-]+\.)+idealista\.(?:com|pt|it)\//i.test(u))continue;
      const im=node('img','report-preview-photo');im.src=u;im.loading='lazy';im.alt='Advertised photo from the listing';im.referrerPolicy='no-referrer';strip.append(im);
    }
    clear($('report-ai-findings'));
    if(!urls.length){status('report-ai-state','OpenData did not include accessible photo URLs in this imported response. No image assessment can be made from the listing facts alone.');return;}
    status('report-ai-state',`${urls.length} listing photo URL(s) found. Requesting a limited AI condition review…`);
    try {
      const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),72000);
      let response;
      try {response=await fetch((window.BYS_API_BASE||'').replace(/\/$/,'')+'/api/listings/photo-review',{
        method:'POST',headers:{'Content-Type':'application/json','X-BYS-Pilot-Code':$('pilot-code').value.trim()},
        body:JSON.stringify({url:result.source_url}),signal:controller.signal,
      });} finally {clearTimeout(timer);}
      const data=await response.json();
      if(response.ok&&data.status==='ok'){renderAI(data);return;}
      status('report-ai-state',data.message||data.reason||'AI inspection is unavailable; the listing photos remain available above.');
    } catch (_) {status('report-ai-state','The AI service could not complete the photo review. The rest of the report remains available.');}
  }

  function reset() {
    const shell=$('property-report');if(shell)shell.hidden=true;
    const old=$('neighborhood');if(old)old.hidden=true;
  }

  document.addEventListener('bys:listing-imported', event=>{
    const result=event.detail||{};
    if(result.status!=='imported'||!result.fields)return;
    const shell=$('property-report');if(!shell)return;
    shell.hidden=false;
    const old=$('neighborhood');if(old)old.hidden=true;
    status('report-property-id','Idealista #'+result.listing_id+' · third-party advertised information · '+(result.retrieved_at?new Date(result.retrieved_at).toLocaleDateString('en-GB'):'date unconfirmed'));
    metrics(result);
    const inputs=['cost-utilities','cost-internet','cost-insurance','cost-other','cost-deposit-months','cost-upfront-extra','cost-income'];
    inputs.forEach(id=>{const el=$(id);if(el)el.oninput=()=>recalcCosts(result);});
    recalcCosts(result);
    neighborhood(result);
    photos(result);
    shell.scrollIntoView({behavior:'smooth',block:'start'});
  });
  document.addEventListener('bys:listing-reset',reset);
})();