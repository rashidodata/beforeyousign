/* BeforeYouSign bilingual interface. Spanish is default; English is selectable.
 * DOM translations preserve the original English strings and never translate
 * source evidence, property names, or the visitor's typed inputs. */
(() => {
  'use strict';
  const phrasePairs = [
    ["Why us","Por qué elegirnos"],["How it works","Cómo funciona"],["Analyze a rental →","Analizar un alquiler →"],
    ["A smarter way to rent","Alquila con más información"],["Don't just find a place.","No te conformes con encontrar piso."],["Know its worth.","Descubre si merece la pena."],
    ["That perfect apartment might be overpriced. Compare rental costs, uncover hidden expenses, and investigate what really matters before you sign.","Ese piso perfecto podría ser demasiado caro. Compara el alquiler, descubre gastos adicionales y comprueba lo que importa antes de firmar."],
    ["Check a property →","Analizar una vivienda →"],["Explore the features","Descubrir las funciones"],["No account required · Free early-access tools · Transparent calculations","Sin registro · Herramientas gratuitas en pruebas · Cálculos transparentes"],
    ["PROPERTY SNAPSHOT","RESUMEN DEL INMUEBLE"],["/ DEMO","/ DEMOSTRACIÓN"],["Renter's view","Vista del inquilino"],["Your next home, understood.","Tu próxima casa, sin sorpresas."],
    ["Compare price · Condition · Neighborhood","Compara precio · Estado · Barrio"],["Rental benchmark","Referencia de alquiler"],["True monthly cost","Coste mensual real"],["Nearby","Cerca"],["Daily essentials","Servicios cotidianos"],
    ["Clear, evidence-based insights.","Conclusiones claras y basadas en datos."],["Not a guess or a sales pitch. Your inputs, your comparisons, your decision.","Sin suposiciones ni discursos de venta. Tus datos, tus comparaciones, tu decisión."],
    ["Start with a link","Empieza con un enlace"],["Paste the listing. We'll handle the numbers.","Pega el anuncio. Analizamos los números."],
    ["BeforeYouSign is built for renters. Start with an Idealista link. We will extract any listing material you provide and distinguish facts from unknowns.","BeforeYouSign está diseñado para inquilinos. Empieza con un enlace de Idealista: separaremos la información disponible de lo que aún no sabemos."],
    ["Idealista rental listing URL","Enlace del anuncio de alquiler de Idealista"],["Private preview code","Código de acceso privado"],
    ["Private pilot · access code required. Retry failed listings; successful results are cached.","Versión privada · Código obligatorio. Puedes reintentar anuncios fallidos; los resultados correctos se guardan en caché."],
    ["Get the listing details without typing them","Obtén los detalles sin escribirlos a mano"],
    ["Attach a screenshot of the Idealista listing's price, features and location. The free text reader runs locally in your browser. Screenshots stay on your device for OCR; extracted text is sent to our analysis API.","Adjunta capturas del precio, las características y la ubicación del anuncio. El lector gratuito procesa las imágenes en tu navegador; solo se envía el texto extraído a nuestra API."],
    ["Listing screenshots (PNG, JPG or WebP; up to 3)","Capturas del anuncio (PNG, JPG o WebP; máximo 3)"],["Or paste the listing description instead","O pega la descripción del anuncio"],["Listing description","Descripción del anuncio"],
    ["Analyze listing →","Analizar anuncio →"],["Try a fictional example","Probar un ejemplo ficticio"],
    ["Paste an Idealista link to begin. If the listing cannot be imported directly, you can add screenshots instead of typing specifications.","Pega un enlace de Idealista para empezar. Si no podemos importar el anuncio, podrás añadir capturas sin tener que escribir los detalles."],
    ["What we found","Lo que hemos encontrado"],["No property loaded yet.","Todavía no se ha cargado ningún inmueble."],
    ["We separate advertised facts from estimates and unknowns. We calculate asking €/m² from supported evidence. If the listing cannot be imported from its URL, attach screenshots instead. Unverified facts remain unknown.","Distinguimos los datos anunciados, las estimaciones y lo que desconocemos. Calculamos el alquiler por m² solo cuando disponemos de información suficiente. Si falla la importación, puedes añadir capturas."],
    ["Your rental due diligence","Tu informe de alquiler"],["Know this home before you sign.","Conoce esta vivienda antes de firmar."],["Property information will appear after import.","La información del inmueble aparecerá tras la importación."],["Evidence-led preview","Informe basado en datos"],
    ["01 · Affordability","01 · Coste y presupuesto"],["What will it really cost?","¿Cuánto te costará realmente?"],
    ["We calculate the advertised rent and separately show any costs you choose to enter. Unknown electricity, water, gas, internet, insurance, deposit and fees are never assumed to be zero.","Calculamos el alquiler anunciado y añadimos por separado los gastos que introduzcas. La luz, el agua, el gas, internet, los seguros, la fianza y las comisiones desconocidos no se consideran gratuitos."],
    ["Electricity / month (€)","Luz / mes (€)"],["Water / month (€)","Agua / mes (€)"],["Gas / month (€)","Gas / mes (€)"],["Internet / month (€)","Internet / mes (€)"],
    ["Insurance / month (€)","Seguro / mes (€)"],["Other bills / month (€)","Otros gastos / mes (€)"],["Deposit (months of rent)","Fianza (meses de alquiler)"],
    ["Other one-off move-in (€)","Otros gastos iniciales (€)"],["Take-home household income (€ / month)","Ingresos netos del hogar (€ / mes)"],
    ["Market rent comparisons require real nearby comparable listings.","Para comparar precios de mercado necesitamos anuncios reales de viviendas similares cercanas."],
    ["02 · Property suitability","02 · Características del inmueble"],["What looks promising—and what needs checking?","Puntos a favor y aspectos por comprobar"],
    ["Advertised advantages","Ventajas anunciadas"],["Questions and potential drawbacks","Preguntas y posibles inconvenientes"],
    ["03 · Neighborhood","03 · Barrio"],["Your everyday neighborhood","Tu día a día en el barrio"],["Preparing nearby-place summary…","Preparando el resumen de lugares cercanos…"],
    ["Retry nearby places (no listing token used)","Reintentar búsqueda de lugares (sin gastar créditos del anuncio)"],
    ["Places come from OpenStreetMap. Distances are straight-line estimates from the advertised map pin, not walking distances. Hours, accessibility, traffic and safety require separate checks.","Lugares obtenidos de OpenStreetMap. Las distancias son aproximadas en línea recta desde el punto anunciado, no distancias a pie. Comprueba horarios, accesibilidad, tráfico y seguridad por separado."],
    ["04 · Visual inspection","04 · Análisis visual"],["What do the photos suggest?","¿Qué muestran las fotos?"],
    ["AI examines only visible details in advertisement photos—never hidden defects, structural safety, legal compliance or exact room dimensions. Confirm important observations in person.","La IA analiza únicamente detalles visibles en las fotos del anuncio. No puede detectar defectos ocultos, confirmar la seguridad estructural, el cumplimiento legal ni las medidas exactas. Comprueba los hallazgos en persona."],
    ["Photo review will start if trusted listing images and an AI service are available.","El análisis empezará cuando haya fotos accesibles y un servicio de IA configurado."],
    ["BeforeYouSign is a decision-support preview, not a valuation, legal opinion or building inspection. Advertised facts are not independently verified.","BeforeYouSign es una herramienta orientativa, no una tasación, asesoría jurídica ni inspección técnica. Los datos de los anuncios no se han verificado de forma independiente."],
    ["Neighborhood essentials","Servicios del barrio"],["A home is more than four walls.","Una casa es mucho más que cuatro paredes."],
    ["After you submit a listing, explore schools, supermarkets, markets, parks and transport near its stated location. If the address is missing, we will tell you.","Tras introducir un anuncio, descubre colegios, supermercados, mercados, parques y transporte cercanos. Si falta la dirección, te lo indicaremos."],
    ["Neighborhood or street (optional)","Barrio o calle (opcional)"],["The property location will be filled in when we can extract it from the supplied listing.","Rellenaremos la ubicación cuando podamos extraerla del anuncio."],
    ["Supermarkets","Supermercados"],["Everyday groceries","Compra diaria"],["Local markets","Mercados locales"],["Food and neighborhood shops","Alimentación y comercio local"],
    ["Schools","Colegios"],["Education options","Centros educativos"],["Nurseries","Guarderías"],["Childcare options","Cuidado infantil"],["Parks","Parques"],["Green spaces nearby","Zonas verdes cercanas"],["Transit","Transporte"],["Metro, bus and rail links","Metro, autobús y tren"],
    ["These links open OpenStreetMap searches, not verified walking routes, distances or individual recommendations.","Estos enlaces abren búsquedas en OpenStreetMap; no son rutas a pie ni recomendaciones verificadas."],
    ["LOCATION CHECKLIST","COMPROBACIONES DEL ENTORNO"],["The right price in the wrong location is still the wrong apartment.","Un buen precio en un mal lugar sigue siendo una mala elección."],
    ["Look beyond straight-line distance: safe walking routes, school catchment rules, shop hours and access to public transport can matter more.","Mira más allá de la distancia en línea recta: las rutas a pie, las zonas escolares, los horarios y el transporte pueden importar más."],
    ["Built for better decisions","Diseñado para decidir mejor"],["All the questions you should ask, in one place.","Todo lo que debes preguntar, en un solo lugar."],["Go beyond listing photos and the advertised monthly rent.","Ve más allá de las fotos y del precio anunciado."],
    ["Is the rent fair?","¿Es razonable el alquiler?"],["See the asking €/m² when rent and area are known. Automatic comparisons to verified local rentals are still in development.","Consulta el precio por m² cuando conozcamos el alquiler y la superficie. Seguimos desarrollando las comparaciones automáticas con anuncios locales."],
    ["What's the real cost?","¿Cuál es el coste real?"],["Spot missing information about fees, deposits and repairs without invented cost estimates.","Detecta gastos, fianzas y reparaciones pendientes sin inventar importes."],
    ["How's the neighborhood?","¿Qué tal es el barrio?"],["Explore supermarkets, markets, schools, nurseries, parks and transit near the address through OpenStreetMap.","Explora supermercados, mercados, colegios, guarderías, parques y transporte mediante OpenStreetMap."],
    ["AI photo assessment","Análisis de fotos con IA"],["Planned analysis of visible light, layout, condition and practical tradeoffs. Requires a separately hosted analysis service.","Análisis de iluminación visible, distribución y estado aparente. Requiere un servicio de IA configurado."],
    ["Pros, cons and uncertainty","Ventajas, inconvenientes y dudas"],["Understand why a property looks expensive or attractive, and what still needs an in-person check.","Comprende qué hace atractiva o cara una vivienda y qué debes comprobar personalmente."],
    ["Evidence you can review","Datos que puedes comprobar"],["Inspect source-labeled listing details and the questions that still need answers.","Revisa los datos del anuncio, sus fuentes y las preguntas pendientes."],
    ["Simple by design","Fácil de usar"],["Three steps to a clearer decision.","Tres pasos para decidir mejor."],["Enter the listing","Introduce el anuncio"],
    ["Paste a rental link. When direct listing access is unavailable, a pasted description is the current fallback.","Pega el enlace de un alquiler. Si la importación falla, puedes pegar su descripción."],
    ["Review extracted facts","Revisa los datos extraídos"],["See the advertised rent, size and features, with evidence and clearly marked unknowns.","Consulta el alquiler, la superficie y las características, indicando lo que falta por confirmar."],
    ["Understand the tradeoffs","Valora los pros y los contras"],["Check asking rent per m² when available, nearby services and questions to verify before signing.","Comprueba el alquiler por m², los servicios cercanos y las dudas antes de firmar."],
    ["BeforeYouSign is an early-stage research tool, not a valuation, survey, legal opinion or guarantee that a property is suitable.","BeforeYouSign es una herramienta experimental, no una tasación, inspección técnica, asesoría legal ni garantía de idoneidad."],
    ["Rent with clarity. Built for curious, careful renters.","Alquila con información. Para inquilinos que quieren decidir mejor."],["BeforeYouSign · Early access prototype","BeforeYouSign · Versión de prueba"],
    ["Monthly rent","Alquiler mensual"],["Asking €/m²","Precio anunciado €/m²"],["Annual rent","Alquiler anual"],["Listed area","Superficie anunciada"],
    ["Unknown","Desconocido"],["Advertised, not independently verified","Anunciado, sin verificar"],["Calculated from advertised values","Calculado a partir del anuncio"],
    ["Excludes utilities and fees","No incluye suministros ni tasas"],["Confirm measured usable area","Confirma la superficie útil"],
    ["Advertised advantages","Ventajas anunciadas"],["Things to check","Aspectos a comprobar"],
    ["Household rent burden","Proporción de ingresos destinada al alquiler"],["Add income","Añade los ingresos"],
    ["Market comparison: unavailable until we have at least three recent, similar nearby rental listings. We will not invent an area median or label this home a bargain.","Comparación de mercado: necesitamos al menos tres alquileres recientes, cercanos y similares. No inventaremos una mediana ni afirmaremos que sea una ganga."],
    ["Supermarkets","Supermercados"],["Groceries for the week","Compra semanal"],["Fresh food and local stalls","Productos frescos y puestos locales"],
    ["Pharmacies","Farmacias"],["Everyday health essentials","Farmacias y salud cotidiana"],["Public transport","Transporte público"],["Getting around","Cómo desplazarse"],
    ["Green space for a break","Zonas verdes para desconectar"],["Schools & nurseries","Colegios y guarderías"],["Education nearby","Educación cercana"],
    ["Cafes","Cafeterías"],["Coffee and third places","Cafés y lugares para reunirse"],
    ["Visible positives","Aspectos positivos visibles"],["Things to check","Aspectos a comprobar"],["Questions to ask the landlord","Preguntas para el propietario"],
    ["No listed advantages have been independently verified.","No se han verificado de forma independiente las ventajas anunciadas."],
    ["Ask about noise, ventilation, service charges and maintenance before signing.","Pregunta por ruido, ventilación, gastos comunitarios y mantenimiento antes de firmar."],
    ["Advertised monthly rent","Alquiler mensual anunciado"],["Monthly subtotal (known inputs)","Subtotal mensual (datos conocidos)"],
    ["Estimated monthly total","Total mensual estimado"],["Year-one recurring subtotal","Subtotal recurrente del primer año"],
    ["Cash needed to move in","Dinero necesario para entrar"],["Rent as % of household income","Alquiler sobre ingresos del hogar"],
    ["Still unknown","Datos aún desconocidos"],["electricity","luz"],["water","agua"],["gas","gas"],["internet","internet"],["insurance","seguro"],["other expenses","otros gastos"],
    ["No photo summary was supplied.","No se ha facilitado un resumen de las fotos."],
    ["Photo review will start if trusted listing images and an AI service are available.","El análisis de fotos comenzará si hay imágenes disponibles y el servicio de IA está configurado."],
    ["No named location in this category was returned within 1.2 km.","No se encontraron lugares con nombre en esta categoría a menos de 1,2 km."],
    ["No usable map coordinates were supplied by the listing provider.","El proveedor no ha facilitado coordenadas utilizables."],
    ["Preparing nearby-place summary…","Preparando el resumen de lugares cercanos…"],
    ["No property loaded yet.","Aún no se ha cargado ningún inmueble."],
    ["Needs confirmation","Pendiente de confirmar"],
    ["Electricity","Luz"],["Water","Agua"],["Gas","Gas"],["Internet","Internet"],["Insurance","Seguro"],
    ["Floor area","Superficie"],["Bedrooms","Habitaciones"],["Bathrooms","Baños"],["Floor","Planta"],
    ["Property summary","Resumen del inmueble"],
    ["No local rental-price verdict is available without comparable evidence.","No podemos valorar el precio sin datos de alquileres comparables."],
  ];
  const translations = new Map(phrasePairs);
  const translated = new WeakMap();
  const skipSelector='script,style,textarea,code,pre,[data-no-translate],.report-places a,.report-preview-photo';
  let locale='es', applying=false;
  const clean=s=>String(s).replace(/\s+/g,' ').trim();
  function dynamic(esOriginal){
    const t=clean(esOriginal);
    if(translations.has(t))return translations.get(t);
    let m;
    if((m=/^Around (.+)$/.exec(t)))return 'Alrededor de '+m[1];
    if((m=/^Imported (\d+) advertised listing facts\./.exec(t)))return 'Se han importado '+m[1]+' datos anunciados del inmueble.';
    if((m=/^Idealista listing #(\d+)$/.exec(t)))return 'Anuncio de Idealista n.º '+m[1];
    if((m=/^Idealista #(\d+) · third-party advertised information · (.+)$/.exec(t)))return 'Idealista n.º '+m[1]+' · datos anunciados por terceros · '+m[2];
    if((m=/^No named location in this category was returned within ([\d.]+) km\.$/.exec(t)))return 'No se han encontrado establecimientos identificados a menos de '+m[1].replace('.',',')+' km.';
    if((m=/^AI reviewed (\d+|\?) advertised image\(s\)\./.exec(t)))return 'La IA ha analizado '+m[1]+' fotos del anuncio. Las conclusiones no equivalen a una inspección técnica.';
    if(t.startsWith('OpenData did not include accessible photo URLs'))return 'OpenData no incluyó enlaces a fotos accesibles. No es posible evaluar las imágenes solo con los datos del anuncio.';
    if(t.startsWith('AI photo review needs an OPENAI_API_KEY'))return 'El análisis de fotos con IA necesita una clave OPENAI_API_KEY configurada en Render. El resto del informe sigue disponible.';
    if(t.startsWith('Nearby places could not be retrieved'))return 'No se han podido obtener lugares cercanos. Puedes reintentar la búsqueda sin gastar créditos de Idealista.';
    if(t.startsWith('OpenStreetMap lookup is temporarily unavailable'))return 'La búsqueda en OpenStreetMap no está disponible temporalmente. Vuelve a intentarlo en unos minutos; no se han inventado distancias.';
    if(t.startsWith('The listing feed does not supply usable coordinates'))return 'El anuncio no proporciona coordenadas suficientes. No podemos calcular las distancias exactas a partir del nombre del barrio.';
    if(t.startsWith('Finding nearby shops'))return 'Buscando comercios, parques y transporte cercanos en OpenStreetMap…';
    if(t.startsWith('Approximate listing location'))return 'Ubicación aproximada del anuncio · distancias en línea recta · OpenStreetMap';
    if(t.startsWith('Advertised map pin'))return 'Punto del mapa del anuncio · distancias en línea recta · OpenStreetMap';
    if(t.startsWith('Distances are straight-line from the provider-listed map pin'))return 'Las distancias son aproximadas en línea recta desde el punto del mapa del anuncio; las rutas a pie pueden ser más largas.';
    if(t.startsWith('Distances are measured from an approximate advertised pin'))return 'Las distancias se calculan desde un punto aproximado del anuncio, no desde la vivienda exacta.';
    if(t.startsWith('The AI service could not complete'))return 'El servicio de IA no ha podido completar el análisis de fotos. El resto del informe sigue disponible.';
    if(t.startsWith('OpenAI rejected the API key'))return 'OpenAI ha rechazado la clave API (HTTP 401). Comprueba OPENAI_API_KEY en Render.';
    if(t.startsWith('OpenAI rate limits or available API credits'))return 'Se ha alcanzado el límite de OpenAI o no hay créditos suficientes (HTTP 429). Revisa los pagos y el uso de la API.';
    if(t.startsWith('The OpenAI API account requires credits'))return 'La cuenta de OpenAI necesita créditos o facturación activa (HTTP 402).';
    if(t.startsWith('The configured OpenAI model is not available'))return 'El modelo de OpenAI configurado no está disponible para este proyecto (HTTP 404).';
    if(t.startsWith('OpenAI rejected the photo request'))return 'OpenAI ha rechazado el análisis de fotos (HTTP 400). Comprueba el formato y la compatibilidad del modelo.';
    if(t.startsWith('The OpenAI API project cannot access'))return 'Este proyecto de OpenAI no tiene permiso para realizar el análisis (HTTP 403).';
    if(t.startsWith('OpenAI photo analysis timed out'))return 'El análisis de fotos de OpenAI ha tardado demasiado.';
    if(t.startsWith('Could not reach OpenAI'))return 'No se ha podido conectar con OpenAI. Revisa la conexión de Render.';
    if(t.startsWith('OpenAI returned an incomplete'))return 'OpenAI ha devuelto un resultado incompleto o hay una foto que no se ha podido procesar.';
    if(t.startsWith('The AI photo review failed during processing'))return 'El análisis de fotos con IA no se ha completado. Consulta las categorías de error en los registros de Render.';
    if(t.startsWith('The OpenAI request timed out upstream'))return 'La petición a OpenAI ha agotado el tiempo de espera (HTTP 504).';
    if(t.startsWith('OpenAI is temporarily unavailable'))return 'OpenAI no está disponible temporalmente (HTTP 503).';
    if(t.startsWith('OpenAI returned a temporary gateway error'))return 'OpenAI ha devuelto un error temporal (HTTP 502).';
    if(t.startsWith('OpenAI is reporting a temporary internal error'))return 'OpenAI ha registrado un error interno temporal (HTTP 500).';
    if(t.startsWith('We could not load nearby places'))return 'No se han podido cargar lugares cercanos. Inténtalo de nuevo más tarde; no se han inventado distancias.';
    if(t.startsWith('The AI photo review failed'))return 'No se ha podido completar el análisis con IA.';
    if(t.startsWith('The advertised photo host did not provide accessible'))return 'No se han podido descargar las fotos del anuncio. No se han gastado créditos de IA.';
    if(t.startsWith('The listing provider did not include usable photo URLs'))return 'El proveedor no ha incluido enlaces a fotos utilizables. La IA no ha analizado imágenes.';
    if(t.startsWith('The shared AI photo review budget'))return 'Se ha alcanzado el límite compartido de análisis con IA por hoy. La importación de anuncios sigue disponible.';
    if(t.startsWith('AI review cache is unavailable'))return 'La caché del análisis con IA no está disponible. No se ha hecho ninguna petición de pago al modelo.';
    if(t.startsWith('Finding nearby shops'))return 'Buscando supermercados, parques, farmacias y transporte en OpenStreetMap…';
    if(t.startsWith('OpenStreetMap lookup is temporarily unavailable'))return 'OpenStreetMap no está disponible en este momento. Prueba de nuevo más tarde; no se han inventado distancias.';
    if(t.startsWith('Monthly rent is unknown'))return 'No conocemos el alquiler mensual; no podemos calcular el coste.';
    if(t.startsWith('Still unknown:'))return 'Aún faltan gastos por confirmar: '+t.slice('Still unknown:'.length);
    if(t.startsWith('All monthly categories have an entered value'))return 'Se han introducido importes en todos los gastos mensuales. Comprueba con el propietario los pagos reales.';
    if(t.startsWith('No listing'))return 'No se ha encontrado un anuncio válido.';
    if(t.startsWith('The property record'))return 'Los datos de este anuncio todavía no están disponibles.';

    if(t.startsWith('The provider did not return'))return 'El proveedor no ha devuelto los datos solicitados. Puedes subir capturas para continuar.';
    if(t.startsWith('The mapped area has limited named points'))return 'Se han encontrado pocos lugares con nombre en el mapa. Esto no significa que falten servicios en la zona.';
    if(t.startsWith('No local rental-price verdict'))return 'No podemos valorar el precio del alquiler sin datos de viviendas comparables.';
    return null;
  }
  function translateNode(node){
    if(node.nodeType!==Node.TEXT_NODE||!node.parentElement||node.parentElement.closest(skipSelector))return;
    const initial=node.nodeValue;const original=translated.get(node)||initial;
    if(!clean(original))return;
    if(!translated.has(node))translated.set(node,original);
    const match=original.match(/^(\s*)([\s\S]*?)(\s*)$/);
    if(!match)return;
    const text=clean(match[2]);const es=translations.get(text)||dynamic(text);
    const value=locale==='es'&&es?match[1]+es+match[3]:original;
    if(node.nodeValue!==value)node.nodeValue=value;
  }
  function translateAttrs(){
    const attrs={
      'import-url':{placeholder:{es:'https://www.idealista.com/inmueble/12345678/'}},
      'pilot-code':{placeholder:{es:'Introduce tu código de acceso'}},
      'import-text':{placeholder:{es:'Opcional: pega aquí la descripción del anuncio.'}},
      'map-location':{placeholder:{es:'p. ej., Malasaña, Madrid'}}
    };
    document.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{
      const a=attrs[el.id];if(!a)return;
      if(!el.dataset.placeholderEn)el.dataset.placeholderEn=el.placeholder;
      const es=a.placeholder?.es;
      if(es)el.placeholder=locale==='es'?es:el.dataset.placeholderEn;
    });
  }
  const walk=()=>{
    applying=true;
    const iterator=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    const nodes=[];while(iterator.nextNode())nodes.push(iterator.currentNode);
    nodes.forEach(translateNode);translateAttrs();applying=false;
  };
  function setLanguage(lang){
    locale=lang==='en'?'en':'es';document.documentElement.lang=locale;
    const selector=document.getElementById('site-language');if(selector)selector.value=locale;
    document.dispatchEvent(new CustomEvent('bys:language-change',{detail:{language:locale}}));
    walk();
  }
  window.BYS_LANGUAGE={get:()=>locale,set:setLanguage};
  document.addEventListener('DOMContentLoaded',()=>{
    const selector=document.getElementById('site-language');
    if(selector)selector.addEventListener('change',()=>setLanguage(selector.value));
    setLanguage('es');
    let scheduled=false;
    new MutationObserver(()=>{
      if(applying||scheduled)return;
      scheduled=true;
      requestAnimationFrame(()=>{scheduled=false;walk();});
    }).observe(document.body,{childList:true,subtree:true,characterData:true});
  });
})();