/* BeforeYouSign: opt-in SmolVLM2-500M WebGPU inference, entirely in this worker.
 * Model weights are downloaded directly from Hugging Face to the visitor's browser.
 * No OpenAI or paid inference service is contacted.
 * Transformers.js API follows Hugging Face's SmolVLM WebGPU worker example.
 */
import {
  AutoProcessor,
  AutoModelForVision2Seq,
  load_image,
} from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/transformers.min.js';

const MODEL = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct';
let bundlePromise = null;
let running = false;

function emit(status, data = {}) { self.postMessage({ status, ...data }); }

async function loadModel() {
  if (bundlePromise) return bundlePromise;
  bundlePromise = (async () => {
    emit('loading', { detail: 'Downloading the SmolVLM2-500M model' });
    if (!self.navigator?.gpu) throw new Error('WEBGPU_UNAVAILABLE');
    const adapter = await self.navigator.gpu.requestAdapter();
    if (!adapter) throw new Error('WEBGPU_UNAVAILABLE');
    const half = adapter.features.has('shader-f16');
    // The official model provides q4 and q4f16 ONNX weights for these modules.
    const dtype = half ? 'q4f16' : 'q4';
    const progress_callback = p => {
      if (!p || typeof p !== 'object') return;
      if (p.status === 'progress' && Number.isFinite(p.progress)) {
        emit('progress', { progress: Math.max(0, Math.min(100, p.progress)), file: String(p.file || '').split('/').pop().slice(0,80) });
      } else if (p.status === 'initiate' || p.status === 'done') {
        emit('model-file', { file: String(p.file || '').split('/').pop().slice(0,80), progressStatus: p.status });
      }
    };
    const processor = await AutoProcessor.from_pretrained(MODEL, { progress_callback });
    const model = await AutoModelForVision2Seq.from_pretrained(MODEL, {
      device: 'webgpu',
      dtype: { embed_tokens: dtype, vision_encoder: dtype, decoder_model_merged: dtype },
      progress_callback,
    });
    emit('ready', { model: MODEL, dtype });
    return [processor, model];
  })();
  try { return await bundlePromise; }
  catch (e) { bundlePromise = null; throw e; }
}

async function analyze(buffer, requestId, language) {
  if (running) { emit('error', { requestId, code: 'BUSY' }); return; }
  running = true;
  try {
    if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 1000 || buffer.byteLength > 2_000_000) {
      throw new Error('INVALID_IMAGE');
    }
    const [processor, model] = await loadModel();
    emit('analyzing', { requestId });
    // Transferred JPEG bytes remain entirely on the visitor's device.
    const image = await load_image(new Blob([buffer], { type: 'image/jpeg' }));
    const prompt = language === 'en'
      ? 'Describe this rental listing photo in three short sentences. Identify the room, visible fixtures and any clearly visible wear or damage. Do not invent defects, mold, noise, dimensions, location or structural conclusions. If unclear, say so.'
      : 'Describe esta foto de un piso en alquiler en tres frases breves en español. Identifica la estancia, elementos visibles y señales de desgaste o daños que se vean claramente. No inventes defectos, moho, ruido, dimensiones ni conclusiones estructurales. Si no se distingue algo, indícalo.';
    const messages = [{ role: 'user', content: [{ type: 'image' }, { type: 'text', text: prompt }] }];
    const text = processor.apply_chat_template(messages, { add_generation_prompt: true });
    const inputs = await processor(text, [image], { do_image_splitting: false });
    const generated = await model.generate({ ...inputs, max_new_tokens: 125, do_sample: false });
    const output = generated?.sequences ?? generated;
    const promptLength = inputs.input_ids.dims.at(-1);
    const answerIds = output.slice(null, [promptLength, null]);
    const answer = processor.batch_decode(answerIds, { skip_special_tokens: true });
    const description = String(answer[0] || '').trim().slice(0, 1700);
    if (!description) throw new Error('EMPTY_OUTPUT');
    emit('result', { requestId, description });
  } catch (error) {
    // Avoid logging arbitrary model URL, keys, or image data.
    const reason = String(error?.message || 'INFERENCE_FAILED');
    const code = /WEBGPU_UNAVAILABLE/.test(reason) ? 'WEBGPU_UNAVAILABLE'
      : /INVALID_IMAGE/.test(reason) ? 'INVALID_IMAGE'
      : /EMPTY_OUTPUT/.test(reason) ? 'EMPTY_OUTPUT'
      : /out of memory|memory allocation|OOM/i.test(reason) ? 'OUT_OF_MEMORY'
      : /fetch|network|download|failed to load|404|403|CORS/i.test(reason) ? 'MODEL_DOWNLOAD_FAILED'
      : 'INFERENCE_FAILED';
    emit('error', { requestId, code });
  } finally {
    running = false;
  }
}

self.addEventListener('message', event => {
  const msg = event.data || {};
  if (msg.type === 'analyze') {
    analyze(msg.buffer, msg.requestId, msg.language === 'en' ? 'en' : 'es');
  }
});