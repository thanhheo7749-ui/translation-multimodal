/* Live audio capture; every ASR input is only PCM already captured by the browser. */
const el=id=>document.getElementById(id);
const state={ready:false,capturing:false,stopping:false,processing:false,session:0,rows:[],history:[],queue:new LiveAudioCore.BoundedQueue(3),dropped:0,stream:null,ctx:null,node:null,sourceNode:null,segmenter:null,pip:null,model:'facebook/nllb-200-distilled-600M',localModel:'facebook/nllb-200-distilled-600M',geminiModel:'gemini-3.5-flash-lite',engineMode:'local',lastAsr:null,lastMt:null,lastLag:null};
const labels={queued:'Chờ xử lý',asr:'Đang nhận dạng',mt:'Đang dịch',ok:'Đã dịch',silence:'Không nhận được lời nói',error:'Lỗi xử lý',skipped:'Bỏ qua để bắt kịp'};
Object.assign(state,{activeRow:null,translating:0,mtQueue:[],pendingWords:[],pendingSince:0,asrDraft:'',stabilizer:new LiveAudioCore.StableWords(),captionInvalid:false,presenter:new LiveAudioCore.CaptionPresenter()});
state.pair=new LiveAudioCore.TranscriptPair();
state.currentSlide=null;
state.slides=[];
state.viewingSlideId=null;

function saveSlidesToStorage() {
  try {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem('live_slides_history', JSON.stringify(state.slides));
    }
  } catch (e) {}
}

function loadSlidesFromStorage() {
  try {
    if (typeof sessionStorage !== 'undefined') {
      const data = sessionStorage.getItem('live_slides_history');
      if (data) {
        const parsed = JSON.parse(data);
        if (Array.isArray(parsed) && parsed.length > 0) {
          state.slides = parsed;
        }
      }
    }
  } catch (e) {}
}
state.vision={active:false,enabled:true,sessionId:'0',sourceEpoch:0,frameIdCounter:0,inFlight:false,sampleTimer:null,pollTimer:null,hiddenVideo:null,videoElement:null,canvas:null,status:'NO_FRAME'};
if(typeof window!=='undefined')window.state=state;
function setSafeText(idOrEl, value) {
  const node = typeof idOrEl === 'string' ? el(idOrEl) : idOrEl;
  if (!node) return;
  const str = String(value ?? '');
  if (node.textContent !== str) {
    node.textContent = str;
  }
}
function error(message){setSafeText('error', message||'');}
function seconds(value){return Number(value).toFixed(1).replace('.',',');}

function getCardBadge(row) {
  if (row.status === 'mt') {
    const isAi = state.engineMode === 'gemini';
    return {
      tag: isAi ? '🧠 Đang dịch AI…' : '⚡ Đang dịch…',
      cardClass: isAi ? 'is-translating' : 'is-draft',
      badgeClass: isAi ? 'is-translating' : 'is-draft'
    };
  }
  if (row.status === 'error') {
    return {
      tag: '⚠️ Lỗi dịch',
      cardClass: 'is-error',
      badgeClass: 'is-error'
    };
  }
  if (row.status === 'skipped') {
    return {
      tag: '⏭️ Bỏ qua',
      cardClass: 'is-draft',
      badgeClass: 'is-draft'
    };
  }
  if (row.provider === 'gemini' || row.provider?.includes('gemini')) {
    return {
      tag: '✨ AI Gemini',
      cardClass: 'is-ai',
      badgeClass: 'badge-ai'
    };
  }
  if (row.provider === 'local-fallback') {
    return {
      tag: '⚡ Dự phòng GPU',
      cardClass: 'is-draft',
      badgeClass: 'is-draft'
    };
  }
  if (row.isDraft) {
    return {
      tag: row.isFinal ? '⚡ Nháp GPU' : '⚡ Đang nghe…',
      cardClass: 'is-draft',
      badgeClass: 'is-draft'
    };
  }
  return {
    tag: labels[row.status] || '✨ Đã dịch',
    cardClass: '',
    badgeClass: 'badge-ok'
  };
}

function renderEntityTags(container, entities, isMic, titleText = '') {
  if (!container) return;
  const key = isMic
    ? '__mic__'
    : (entities && entities.length
        ? entities.map(e => (typeof e === 'string' ? e : (e.text || e.label || ''))).filter(Boolean).join('|') + '::' + String(titleText || '')
        : '__empty__');
  if (container._renderedKey === key) return;
  container._renderedKey = key;

  if (typeof container.replaceChildren === 'function') {
    if (isMic) {
      const tag = document.createElement('span');
      tag.className = 'entity-badge placeholder';
      tag.textContent = 'Không có từ khóa (chế độ micro)';
      container.replaceChildren(tag);
      return;
    }
    if (!entities || !entities.length) {
      const tag = document.createElement('span');
      tag.className = 'entity-badge placeholder';
      tag.textContent = 'Chưa có từ khóa';
      container.replaceChildren(tag);
      return;
    }
    const tags = [];
    const seen = new Set();
    const cleanTitle = (titleText || '').trim().toLowerCase().replace(/\s+/g, '');
    for (const ent of entities) {
      const text = typeof ent === 'string' ? ent : (ent.text || ent.label || '');
      const trimmed = text.trim();
      if (!trimmed || trimmed.length <= 1) continue;
      const lower = trimmed.toLowerCase();
      const compact = lower.replace(/\s+/g, '');
      // Bỏ qua nếu từ khóa trùng với tiêu đề slide đang hiển thị ở trên
      if (cleanTitle && (compact === cleanTitle || lower === (titleText || '').trim().toLowerCase())) continue;
      // Khử trùng lặp từ khóa
      if (seen.has(compact)) continue;
      seen.add(compact);
      const tag = document.createElement('span');
      tag.className = 'entity-badge';
      tag.textContent = trimmed;
      tags.push(tag);
    }
    if (!tags.length) {
      const tag = document.createElement('span');
      tag.className = 'entity-badge placeholder';
      tag.textContent = 'Chưa có từ khóa riêng';
      tags.push(tag);
    }
    container.replaceChildren(...tags);
  }
}

function renderSlideChips(container, activeSlide) {
  if (!container) return;
  const key = (!state.slides || !state.slides.length)
    ? '__empty__'
    : state.slides.map(s => `${s.slide_id}:${s.title}:${s.isUserEdited ? 1 : 0}:${activeSlide && s.slide_id === activeSlide.slide_id ? 1 : 0}`).join('|');
  if (container._renderedKey === key) return;
  container._renderedKey = key;

  if (!state.slides || !state.slides.length) {
    if (typeof container.replaceChildren === 'function') {
      const placeholder = document.createElement('span');
      placeholder.className = 'slide-chip placeholder';
      placeholder.textContent = 'Chưa có slide';
      container.replaceChildren(placeholder);
    }
    return;
  }

  const chips = [];
  for (let i = 0; i < state.slides.length; i++) {
    const s = state.slides[i];
    const chip = document.createElement('button');
    chip.type = 'button';
    const isActive = Boolean(activeSlide && s.slide_id === activeSlide.slide_id);
    let className = 'slide-chip';
    if (isActive) className += ' active';
    if (s.isUserEdited) className += ' is-edited';
    chip.className = className;

    const shortTitle = s.title ? (s.title.length > 18 ? s.title.slice(0, 18) + '…' : s.title) : `Slide #${s.slide_id}`;
    chip.textContent = `${s.isUserEdited ? '✏️ ' : ''}#${s.slide_id}: ${shortTitle}`;
    chip.title = `Xem lại Slide #${s.slide_id}: ${s.title || ''}`;
    chip.onclick = () => {
      state.viewingSlideId = s.slide_id;
      renderSlideInspector();
    };
    chips.push(chip);
  }
  if (typeof container.replaceChildren === 'function') {
    container.replaceChildren(...chips);
  }
}

function initSlideNavButtons() {
  const prevBtn = el('slide-prev-btn');
  const nextBtn = el('slide-next-btn');
  if (prevBtn) {
    prevBtn.onclick = () => {
      if (!state.slides || !state.slides.length) return;
      let activeSlide = (state.viewingSlideId !== null ? state.slides.find(s => s.slide_id === state.viewingSlideId) : null) || state.slides[state.slides.length - 1];
      let activeIdx = state.slides.findIndex(s => s.slide_id === activeSlide?.slide_id);
      if (activeIdx > 0) {
        state.viewingSlideId = state.slides[activeIdx - 1].slide_id;
        renderSlideInspector();
      }
    };
  }
  if (nextBtn) {
    nextBtn.onclick = () => {
      if (!state.slides || !state.slides.length) return;
      let activeSlide = (state.viewingSlideId !== null ? state.slides.find(s => s.slide_id === state.viewingSlideId) : null) || state.slides[state.slides.length - 1];
      let activeIdx = state.slides.findIndex(s => s.slide_id === activeSlide?.slide_id);
      if (activeIdx >= 0 && activeIdx < state.slides.length - 1) {
        state.viewingSlideId = state.slides[activeIdx + 1].slide_id;
        renderSlideInspector();
      }
    };
  }
}

function renderSlideInspector() {
  const statusEl = el('slide-status');
  const titleEl = el('slide-title');
  const entitiesEl = el('slide-entities');
  const counterEl = el('slide-nav-counter');
  const chipsEl = el('slide-chips');
  const prevBtn = el('slide-prev-btn');
  const nextBtn = el('slide-next-btn');
  if (!statusEl && !titleEl && !entitiesEl) return;

  // Determine active viewing slide
  let activeSlide = null;
  if (state.viewingSlideId !== null && state.slides && state.slides.length) {
    activeSlide = state.slides.find(s => s.slide_id === state.viewingSlideId) || null;
  }
  if (!activeSlide) {
    if (state.slides && state.slides.length > 0) {
      activeSlide = state.slides[state.slides.length - 1];
    } else {
      activeSlide = state.currentSlide;
    }
  }

  let statusText = 'Chờ hình ảnh';
  let statusClass = 'slide-badge badge-idle';
  let titleText = 'Chưa phát hiện slide';
  let entities = [];

  const isEnabled = state.vision?.enabled !== false;
  const isMic = state.capturing && state.kind === 'mic';
  if (!isEnabled) {
    if (activeSlide?.title || (activeSlide?.entities && activeSlide.entities.length)) {
      statusText = 'Tạm dừng quét';
      statusClass = 'slide-badge badge-idle';
      titleText = activeSlide.title || '(Không có tiêu đề slide)';
      entities = activeSlide.entities || [];
    } else {
      statusText = 'Đã tắt quét';
      statusClass = 'slide-badge badge-idle';
      titleText = 'Đã tạm tắt quét OCR (tiết kiệm CPU). Bật lại ở mục "Quét OCR" góc trên để nhận diện slide.';
      entities = [];
    }
  } else if (isMic) {
    statusText = 'OCR cần nguồn hình ảnh';
    statusClass = 'slide-badge badge-mic';
    titleText = 'Chế độ Micro: OCR cần nguồn hình ảnh (Chia sẻ Tab hoặc Video).';
  } else if (!state.capturing) {
    if (activeSlide?.title || (activeSlide?.entities && activeSlide.entities.length)) {
      statusText = `Đã lưu ${state.slides.length || 1} slide`;
      statusClass = 'slide-badge badge-ready';
      titleText = activeSlide.title || '(Không có tiêu đề slide)';
      entities = activeSlide.entities || [];
    } else {
      statusText = 'Chờ hình ảnh';
      statusClass = 'slide-badge badge-idle';
      titleText = 'Chưa phát hiện slide';
      entities = [];
    }
  } else {
    const snap = state.currentSlide;
    const vStatus = state.vision?.status || 'NO_FRAME';
    if (vStatus === 'STABILIZING') {
      statusText = 'Đang ổn định';
      statusClass = 'slide-badge badge-stabilizing';
      titleText = activeSlide?.title ? activeSlide.title + ' (đang chuyển cảnh…)' : 'Đang ổn định khung hình…';
      entities = activeSlide?.entities || [];
    } else if (vStatus === 'OCR_PENDING') {
      statusText = 'Đang trích xuất chữ';
      statusClass = 'slide-badge badge-stabilizing';
      titleText = activeSlide?.title || 'Đang trích xuất chữ…';
      entities = activeSlide?.entities || [];
    } else if (vStatus === 'EMPTY' || snap?.status === 'EMPTY') {
      if (state.viewingSlideId !== null && activeSlide) {
        statusText = `Đã lưu Slide #${activeSlide.slide_id}`;
        statusClass = 'slide-badge badge-ready';
        titleText = activeSlide.title || '(Không có tiêu đề slide)';
        entities = activeSlide.entities || [];
      } else {
        statusText = 'Không có chữ';
        statusClass = 'slide-badge badge-empty';
        titleText = 'Không có chữ trên slide.';
        entities = [];
      }
    } else if (vStatus === 'ERROR' || snap?.status === 'ERROR') {
      statusText = 'Lỗi nhận dạng';
      statusClass = 'slide-badge badge-error';
      titleText = activeSlide?.title || 'Không thể trích xuất chữ từ frame này.';
      entities = activeSlide?.entities || [];
    } else if (activeSlide?.status === 'READY' || snap?.status === 'READY') {
      statusText = 'Đã trích xuất chữ';
      statusClass = 'slide-badge badge-ready';
      titleText = activeSlide?.title || '(Không có tiêu đề slide)';
      entities = activeSlide?.entities || [];
    } else {
      statusText = 'Chờ hình ảnh';
      statusClass = 'slide-badge badge-idle';
      titleText = activeSlide?.title || 'Chưa phát hiện slide';
      entities = activeSlide?.entities || [];
    }
  }

  if (statusEl) {
    if (statusEl.textContent !== statusText) statusEl.textContent = statusText;
    if (statusEl.className !== statusClass) statusEl.className = statusClass;
  }
  if (titleEl) {
    setSafeText(titleEl, titleText);
  }
  if (entitiesEl) {
    renderEntityTags(entitiesEl, entities, isMic, titleText);
  }

  // Update navigation counter & buttons
  const totalSlides = state.slides ? state.slides.length : 0;
  if (counterEl) {
    const activeIdx = activeSlide && state.slides ? state.slides.findIndex(s => s.slide_id === activeSlide.slide_id) : -1;
    const pos = activeIdx >= 0 ? `${activeIdx + 1}/${totalSlides}` : `${totalSlides} slide`;
    setSafeText(counterEl, totalSlides ? `Slide ${pos}` : '0 slide');
  }

  if (prevBtn && nextBtn) {
    const activeIdx = activeSlide && state.slides ? state.slides.findIndex(s => s.slide_id === activeSlide.slide_id) : -1;
    prevBtn.disabled = activeIdx <= 0;
    nextBtn.disabled = activeIdx < 0 || activeIdx >= totalSlides - 1;
  }

  if (chipsEl) {
    renderSlideChips(chipsEl, activeSlide);
  }

  const scanIndicator = el('slide-scan-indicator');
  if (scanIndicator) {
    const isScanning = state.capturing && state.vision && state.vision.active && isEnabled;
    if (isScanning) {
      scanIndicator.style.display = 'inline-flex';
      const frameCount = state.vision.frameIdCounter || 0;
      setSafeText('slide-frames-count', `(2 fps · ${frameCount} frames)`);
    } else {
      scanIndicator.style.display = 'none';
      setSafeText('slide-frames-count', '');
    }
  }
}

function initSlideToggle() {
  const toggleBtn = el('slide-toggle');
  if (toggleBtn) {
    toggleBtn.onclick = () => {
      const body = el('slide-panel-body');
      if (!body) return;
      const isCollapsed = String(body.className || '').includes('is-collapsed');
      body.className = isCollapsed ? 'slide-panel-body' : 'slide-panel-body is-collapsed';
      if (typeof toggleBtn.setAttribute === 'function') {
        toggleBtn.setAttribute('aria-expanded', isCollapsed ? 'true' : 'false');
      }
      const txt = typeof toggleBtn.querySelector === 'function' ? toggleBtn.querySelector('.toggle-text') : null;
      const arrow = typeof toggleBtn.querySelector === 'function' ? toggleBtn.querySelector('.toggle-arrow') : null;
      if (txt) txt.textContent = isCollapsed ? 'Thu gọn' : 'Mở rộng';
      if (arrow) arrow.textContent = isCollapsed ? '▼' : '▶';
    };
  }

  const enableCheckbox = el('slide-enable-checkbox');
  if (enableCheckbox) {
    enableCheckbox.addEventListener('change', e => {
      if (state.vision) {
        state.vision.enabled = e.target.checked;
        if (!state.vision.enabled) {
          state.vision.status = 'PAUSED';
        } else {
          state.vision.status = state.currentSlide ? (state.currentSlide.status || 'READY') : 'NO_FRAME';
        }
        renderSlideInspector();
      }
    });
  }
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>'"]/g, tag => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[tag] || tag));
}

function initOcrModal() {
  const inspectBtn = el('slide-inspect-btn');
  const modal = el('ocr-modal');
  const closeBtn = el('ocr-modal-close');
  const cancelBtn = el('ocr-modal-cancel');
  const backdrop = el('ocr-modal-backdrop');
  const saveBtn = el('ocr-modal-save');
  const heading = el('ocr-modal-heading');
  const titleInput = el('ocr-edit-title');
  const entitiesInput = el('ocr-edit-entities');
  const rawList = el('ocr-raw-list');
  const feedback = el('ocr-modal-feedback');

  if (!inspectBtn || !modal) return;

  function closeModal() {
    modal.hidden = true;
    if (feedback) feedback.textContent = '';
  }

  function getTargetSlide() {
    if (state.viewingSlideId !== null && state.slides && state.slides.length) {
      const found = state.slides.find(s => s.slide_id === state.viewingSlideId);
      if (found) return found;
    }
    if (state.slides && state.slides.length > 0) {
      return state.slides[state.slides.length - 1];
    }
    return state.currentSlide;
  }

  function openModal() {
    modal.hidden = false;
    if (feedback) feedback.textContent = '';
    const snap = getTargetSlide();
    const title = snap?.title || '';
    if (titleInput) titleInput.value = title;

    if (heading) {
      const sId = snap?.slide_id || (state.slides?.length ? state.slides.length : 1);
      heading.textContent = `Chi tiết & Chỉnh sửa Ngữ cảnh - Slide #${sId}${snap?.isUserEdited ? ' (Đã sửa)' : ''}`;
    }

    const entities = snap?.entities || [];
    const textList = entities.map(e => typeof e === 'string' ? e : (e.text || '')).filter(Boolean);
    if (entitiesInput) entitiesInput.value = textList.join(', ');

    if (rawList) {
      if (!entities.length) {
        rawList.innerHTML = '<p class="muted" style="padding:10px;text-align:center;color:#64748b;">Chưa có dòng chữ nào được quét từ slide này.</p>';
      } else {
        const items = entities.map(e => {
          const txt = typeof e === 'string' ? e : (e.text || '');
          const score = typeof e === 'object' && e.score !== undefined ? `${Math.round(e.score * 100)}%` : '100%';
          return `<div class="ocr-raw-item"><span>${escapeHtml(txt)}</span><span class="ocr-raw-score">${score}</span></div>`;
        });
        rawList.innerHTML = items.join('');
      }
    }
  }

  inspectBtn.onclick = openModal;
  if (closeBtn) closeBtn.onclick = closeModal;
  if (cancelBtn) cancelBtn.onclick = closeModal;
  if (backdrop) backdrop.onclick = closeModal;

  if (saveBtn) {
    saveBtn.onclick = async () => {
      const newTitle = (titleInput?.value || '').trim();
      const rawEntities = (entitiesInput?.value || '').split(',').map(s => s.trim()).filter(Boolean);
      saveBtn.disabled = true;
      if (feedback) feedback.textContent = 'Đang lưu…';

      try {
        let snap = getTargetSlide();
        const formattedEntities = rawEntities.map(t => ({ text: t, score: 1.0, box: [] }));

        if (!snap) {
          const newId = (state.slides ? state.slides.length : 0) + 1;
          snap = {
            session_id: String(state.session),
            source_epoch: state.vision?.sourceEpoch || 0,
            status: 'READY',
            slide_id: newId,
            slide_revision: 1,
            title: newTitle,
            entities: formattedEntities,
            isUserEdited: true
          };
          if (!state.slides) state.slides = [];
          state.slides.push(snap);
          state.currentSlide = snap;
          state.viewingSlideId = newId;
        } else {
          snap.title = newTitle;
          snap.entities = formattedEntities;
          snap.status = 'READY';
          snap.isUserEdited = true;
          if (!state.slides) state.slides = [];
          if (!state.slides.some(s => s.slide_id === snap.slide_id)) {
            state.slides.push(snap);
          }
          if (state.currentSlide && state.currentSlide.slide_id === snap.slide_id) {
            state.currentSlide.title = newTitle;
            state.currentSlide.entities = formattedEntities;
            state.currentSlide.status = 'READY';
          }
        }

        saveSlidesToStorage();
        renderSlideInspector();

        await requestJSON('/api/live/vision/override', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: String(state.session),
            source_epoch: state.vision?.sourceEpoch || 0,
            slide_id: snap.slide_id,
            title: newTitle,
            entities: rawEntities
          })
        });

        if (feedback) feedback.textContent = '✅ Đã lưu slide vĩnh viễn!';
        setTimeout(closeModal, 600);
      } catch (err) {
        console.warn('Override error:', err);
        if (feedback) feedback.textContent = '✅ Đã lưu cục bộ (offline)';
        setTimeout(closeModal, 600);
      } finally {
        saveBtn.disabled = false;
      }
    };
  }
}

function renderVideoCaption(){
  const video = el('demo-video');
  const mediaTime = video ? (video.currentTime || 0) : 0;
  const latest = state.presenter.select(state.rows, mediaTime, performance.now());
  const visible = state.kind === 'video' && !state.captionInvalid && !!latest;
  const captionsEl = el('video-captions');
  if (captionsEl && captionsEl.hidden !== !visible) {
    captionsEl.hidden = !visible;
  }
  setSafeText('caption-en', visible ? (latest.en || '') : '');
  setSafeText('caption-vi', visible ? (latest.vi || '') : '');
  setSafeText('caption-note', visible ? `Sau lời nói ${seconds(Math.max(0, mediaTime - latest.mediaEnd))} giây` : 'Đang nghe và dịch…');
  const late = state.rows.filter(row => row.lateForVideo).length;
  setSafeText('caption-health', late ? `${late} bản dịch trễ hơn 2,5 giây. Phụ đề có ghi độ trễ; kết quả về sau không làm quay lại câu cũ.` : 'Phụ đề xuất hiện khi có kết quả, giữ tối thiểu 0,9 giây để đọc; độ trễ ghi ngay trên phụ đề.');
  renderFloating();
}
function renderFloating(){
  if(!state.pip||state.pip.closed)return;
  const doc=state.pip.document;
  const put=(id,value)=>{const node=doc.getElementById(id);if(node&&node.textContent!==value)node.textContent=value;};
  put('state',el('state')?.textContent||'');
  const stop=doc.getElementById('stop'),share=doc.getElementById('pip-share');
  if(stop && stop.disabled !== (!state.capturing||state.stopping)) stop.disabled=!state.capturing||state.stopping;
  if(share){
    const shouldHide = state.capturing;
    if(share.hidden !== shouldHide) share.hidden = shouldHide;
    const shouldDisable = !state.ready||state.processing||!!state.translating||state.stopping;
    if(share.disabled !== shouldDisable) share.disabled = shouldDisable;
  }
  put('pip-error',el('error')?.textContent||'');

  const hearing=state.asrDraft||state.pendingWords.map(w=>w.text).join(' ')||'';
  put('draft-bar',hearing?`🎙️ Đang nghe: ${hearing}`:'');

  const matched=state.pair.select(state.rows,performance.now());
  if(matched){
    put('en',matched.en||'');
    put('vi',matched.vi||'');
  }else{
    put('en','');
    put('vi','');
  }
}
function updateControls(){
  const isCapturing = state.capturing;
  const setDisabled = (id, val) => {
    const n = el(id);
    if (n && n.disabled !== val) n.disabled = val;
  };
  setDisabled('share', !state.ready || state.stopping || (isCapturing && state.kind !== 'tab'));
  setDisabled('mic', !state.ready || state.stopping || (isCapturing && state.kind !== 'mic'));
  setDisabled('demo-start', !state.ready || state.stopping || (isCapturing && state.kind !== 'video'));
  setDisabled('stop', !isCapturing || state.stopping);
  setDisabled('chunk', isCapturing);
  setDisabled('export', !state.rows.length);
}

const timelineCards = new Map();

function renderTimeline() {
  const timeline = el('timeline');
  if (!timeline) return;

  if (!state.rows.length) {
    if (timelineCards.size > 0) {
      timelineCards.clear();
    }
    if (!timeline._hasEmpty) {
      if (typeof timeline.replaceChildren === 'function') {
        const empty = document.createElement('p');
        empty.className = 'muted empty-note';
        empty.textContent = 'Chưa có lịch sử. Phát âm thanh hoặc nói để xem nhật ký dịch tại đây.';
        timeline.replaceChildren(empty);
      }
      timeline._hasEmpty = true;
    }
    return;
  }

  if (timeline._hasEmpty) {
    if (typeof timeline.replaceChildren === 'function') {
      timeline.replaceChildren();
    }
    timeline._hasEmpty = false;
  }

  const recentRows = state.rows.slice(-80).reverse();
  const activeIds = new Set(recentRows.map(r => r.id));

  for (const [id, cached] of timelineCards.entries()) {
    if (!activeIds.has(id)) {
      if (typeof cached.card.remove === 'function') cached.card.remove();
      timelineCards.delete(id);
    }
  }

  for (let i = recentRows.length - 1; i >= 0; i--) {
    const row = recentRows[i];
    let cached = timelineCards.get(row.id);
    if (!cached) {
      const card = document.createElement('article');
      card.id = `log-card-${row.id}`;
      const top = document.createElement('div');
      top.className = 'card-top';
      const time = document.createElement('span');
      const badge = document.createElement('span');
      top.append(time, badge);
      card.append(top);
      const en = document.createElement('p');
      en.className = 'en';
      card.append(en);
      const vi = document.createElement('p');
      card.append(vi);
      const timing = document.createElement('div');
      timing.className = 'timing';
      card.append(timing);

      cached = { card, time, badge, en, vi, timing };
      timelineCards.set(row.id, cached);

      if (timeline.firstChild && typeof timeline.insertBefore === 'function') {
        timeline.insertBefore(card, timeline.firstChild);
      } else if (typeof timeline.prepend === 'function') {
        timeline.prepend(card);
      } else {
        timeline.append(card);
      }
    }

    const badgeInfo = getCardBadge(row);
    const cardClass = 'card ' + (badgeInfo.cardClass || '');
    if (cached.card.className !== cardClass) cached.card.className = cardClass;

    const slideTag = row.slideTitle ? ` · 🏷️ #${row.slideId || ''} ${row.slideTitle.length > 20 ? row.slideTitle.slice(0, 20) + '…' : row.slideTitle}` : '';
    const timeText = `#${row.id} · ${seconds(row.startSec)}s${slideTag}`;
    if (cached.time.textContent !== timeText) cached.time.textContent = timeText;

    const badgeClass = 'badge ' + (badgeInfo.badgeClass || '');
    if (cached.badge.className !== badgeClass) cached.badge.className = badgeClass;
    if (cached.badge.textContent !== badgeInfo.tag) cached.badge.textContent = badgeInfo.tag;

    const enText = row.en || '…';
    if (cached.en.textContent !== enText) cached.en.textContent = enText;

    const viClass = row.status === 'error' ? 'error' : 'vi';
    if (cached.vi.className !== viClass) cached.vi.className = viClass;
    const viText = row.vi || row.message || (row.status === 'mt' ? 'Đang dịch…' : '');
    if (cached.vi.textContent !== viText) cached.vi.textContent = viText;

    const timingText = `Thu ${seconds(row.durationSec)}s${row.asrMs !== undefined ? ' · ASR ' + Math.round(row.asrMs) + 'ms' : ''}${row.mtMs !== undefined ? ' · MT ' + Math.round(row.mtMs) + 'ms' : ''}${row.lagMs !== undefined ? ' · Sau ASR ' + seconds(row.lagMs / 1000) + 's' : ''}`;
    if (cached.timing.textContent !== timingText) cached.timing.textContent = timingText;
  }
}

function render(){
  updateControls();
  renderVideoCaption();
  renderSlideInspector();
  setSafeText('queue', `ASR ${state.queue.length}${state.processing?'+1':''} · Dịch ${state.mtQueue.length} chờ + ${state.translating} chạy`);
  setSafeText('dropped', state.dropped);
  setSafeText('asr', state.lastAsr===null?'Chưa đo':`${Math.round(state.lastAsr)} ms`);
  setSafeText('mt', state.lastMt===null?'Chưa đo':`${Math.round(state.lastMt)} ms`);
  setSafeText('lag', state.lastLag===null?'Chưa đo':`${seconds(state.lastLag/1000)} giây`);
  const current=[...state.rows].reverse().find(row=>row.en);
  const source=current?.en||'Chưa có lời nói.';
  setSafeText('asr-draft', 'Nhận dạng nháp (có thể sửa): '+(state.asrDraft||'đang nghe tiếp…'));
  const target=current?(current.vi||(current.status==='mt'?'Đang dịch đoạn này…':current.message||'Chưa có bản dịch.')):'Bản dịch sẽ xuất hiện tại đây.';
  setSafeText('current-en', source);
  setSafeText('current-vi', target);
  setSafeText('current-status', current?`Đoạn ${current.id} · ${labels[current.status]} · mốc thu ${seconds(current.startSec)}–${seconds(current.endSec)}s`:'');
  setSafeText('log-count', `${state.rows.filter(r=>r.en).length} đoạn`);
  renderTimeline();
}
async function requestJSON(path,options={}){
  const response=await fetch(path,options);let data;
  try{data=await response.json();}catch{throw new Error('Server trả dữ liệu không hợp lệ. Dừng server cũ và mở lại studio.cmd.');}
  if(!response.ok||data.status==='error'){const e=new Error(data.message||'Request không thành công.');e.code=data.error_code;e.diagnostic=data.diagnostic;throw e;}
  return data;
}
function enqueue(job){
  if(!job)return;
  job.session=state.session;job.queuedAt=performance.now();
  job.mediaOffset=state.kind==='video'?el('demo-video').currentTime-job.endSec:null;
  // Pending snapshots overlap: retain the freshest audio, not stale ASR work.
  state.queue.items=[job];
  render();processQueue();
}
function consumePendingWords(final = false) {
  if (!state.pendingWords.length) {
    if (final && state.activeRow && !state.activeRow.isFinal) {
      state.activeRow.isFinal = true;
      const finishedRow = state.activeRow;
      state.activeRow = null;
      triggerRowTranslation(finishedRow);
    }
    return;
  }

  while (state.pendingWords.length > 0) {
    if (!state.activeRow) {
      const first = state.pendingWords[0];
      const currentActiveSlide = (state.slides && state.slides.length > 0) ? state.slides[state.slides.length - 1] : state.currentSlide;
      state.activeRow = {
        id: state.rows.length + 1,
        session: state.session,
        startSec: first.start,
        mediaStart: first.mediaStart,
        slideId: currentActiveSlide?.slide_id || null,
        slideTitle: currentActiveSlide?.title || '',
        status: 'mt',
        en: '',
        vi: '',
        isDraft: true,
        isFinal: false,
        isPolished: false,
        words: [],
        asrMs: state.lastAsr,
        updatedAt: performance.now()
      };
      state.rows.push(state.activeRow);
    }

    const cutIdx = LiveAudioCore.findSentenceBoundary(state.pendingWords, final);
    if (cutIdx >= 0) {
      const chunk = state.pendingWords.splice(0, cutIdx + 1);
      state.activeRow.words.push(...chunk);
      state.activeRow.en = state.activeRow.words.map(w => w.text).join(' ').trim();
      const last = state.activeRow.words[state.activeRow.words.length - 1];
      state.activeRow.endSec = last.end;
      state.activeRow.mediaEnd = last.mediaEnd;
      state.activeRow.durationSec = state.activeRow.endSec - state.activeRow.startSec;
      state.activeRow.receivedAt = last.receivedAt;
      state.activeRow.updatedAt = performance.now();
      state.activeRow.isFinal = true;

      const finishedRow = state.activeRow;
      state.activeRow = null;
      triggerRowTranslation(finishedRow);
    } else {
      const chunk = state.pendingWords.splice(0, state.pendingWords.length);
      state.activeRow.words.push(...chunk);
      state.activeRow.en = state.activeRow.words.map(w => w.text).join(' ').trim();
      const last = state.activeRow.words[state.activeRow.words.length - 1];
      state.activeRow.endSec = last.end;
      state.activeRow.mediaEnd = last.mediaEnd;
      state.activeRow.durationSec = state.activeRow.endSec - state.activeRow.startSec;
      state.activeRow.receivedAt = last.receivedAt;
      state.activeRow.updatedAt = performance.now();

      const ageMs = performance.now() - (state.activeRow.updatedAt || performance.now());
      if (LiveAudioCore.phraseReady(state.activeRow.words, final, ageMs)) {
        triggerRowTranslation(state.activeRow);
      }
      break;
    }
  }
  state.pendingSince = 0;
  render();
}

function triggerRowTranslation(row) {
  if (!row || row.session !== state.session) return;
  if (row.isTranslating) {
    row.needsRetranslate = true;
    return;
  }
  const text = row.en;
  if (!text) return;
  if (text === row.lastTranslatedEn && row.status === 'ok') {
    return;
  }

  // Bounded MT concurrency: limit max 2 concurrent translation requests
  if (state.translating >= 2) {
    if (!state.mtQueue.includes(row)) {
      state.mtQueue.push(row);
    }
    render();
    return;
  }

  executeRowTranslation(row);
}

async function executeRowTranslation(row) {
  if (!row || row.session !== state.session) return;
  const text = row.en;
  if (!text) return;

  state.translating++;
  row.isTranslating = true;
  row.needsRetranslate = false;
  row.status = 'mt';
  render();

  const rawMode = el('engine-mode')?.value;
  const mode = ['local', 'hybrid', 'gemini'].includes(rawMode) ? rawMode : (state.engineMode || 'local');
  const context = state.rows.filter(r => r.id < row.id && r.en).slice(-2).map(r => r.en).join(' ').slice(-3000);

  const sourceEpoch = (state.vision && Number.isInteger(state.vision.sourceEpoch)) ? state.vision.sourceEpoch : 0;
  const segStartMs = Math.round((row.startSec || 0) * 1000);
  const segEndMs = Math.round((row.endSec || 0) * 1000);

  try {
    // -------------------------------------------------------------
    // CHẾ ĐỘ 1: LOCAL (⚡ Local NLLB siêu tốc 150ms)
    // -------------------------------------------------------------
    if (mode === 'local') {
      const translation = await requestJSON('/api/translate-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          previous_context: context,
          provider: 'local',
          model: state.localModel || 'facebook/nllb-200-distilled-600M',
          mode: 'stream',
          source_epoch: sourceEpoch,
          segment_audio_start_ms: segStartMs,
          segment_audio_end_ms: segEndMs
        })
      });
      if (row.session !== state.session) return;
      row.lastTranslatedEn = text;
      row.vi = translation.translated_text;
      row.status = 'ok';
      row.provider = 'local';
      row.isDraft = !row.isFinal;
      row.mtMs = translation.latency_ms;
      row.displayedAt = performance.now();
      row.lagMs = performance.now() - (row.receivedAt || performance.now());
      state.lastMt = row.mtMs;
      state.lastLag = row.lagMs;
      row.lateForVideo = state.kind === 'video' && el('demo-video').currentTime > row.mediaEnd + 2.5;
      render();
    }
    // -------------------------------------------------------------
    // CHẾ ĐỘ 2: HYBRID (🚀 Local trước 150ms + Gemini hiệu chỉnh bất đồng bộ ở nền)
    // -------------------------------------------------------------
    else if (mode === 'hybrid') {
      const translation = await requestJSON('/api/translate-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          previous_context: context,
          provider: 'local',
          model: state.localModel || 'facebook/nllb-200-distilled-600M',
          mode: 'stream',
          source_epoch: sourceEpoch,
          segment_audio_start_ms: segStartMs,
          segment_audio_end_ms: segEndMs
        })
      });
      if (row.session !== state.session) return;
      row.lastTranslatedEn = text;
      row.vi = translation.translated_text;
      row.status = 'ok';
      row.provider = 'local';
      row.isDraft = !row.isFinal;
      row.mtMs = translation.latency_ms;
      row.displayedAt = performance.now();
      row.lagMs = performance.now() - (row.receivedAt || performance.now());
      state.lastMt = row.mtMs;
      state.lastLag = row.lagMs;
      row.lateForVideo = state.kind === 'video' && el('demo-video').currentTime > row.mediaEnd + 2.5;
      render();

      if (row.isFinal && !row.isPolished) {
        polishRowWithGemini(row);
      }
    }
    // -------------------------------------------------------------
    // CHẾ ĐỘ 3: GEMINI (🧠 Gemini Cloud trực tiếp)
    // -------------------------------------------------------------
    else if (mode === 'gemini') {
      row.isDraft = false;
      const translation = await requestJSON('/api/translate-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          previous_context: context,
          provider: 'gemini',
          model: state.geminiModel || 'gemini-3.5-flash-lite',
          mode: 'stream',
          source_epoch: sourceEpoch,
          segment_audio_start_ms: segStartMs,
          segment_audio_end_ms: segEndMs
        })
      });
      if (row.session !== state.session) return;
      row.lastTranslatedEn = text;
      row.vi = translation.translated_text;
      row.status = 'ok';
      row.provider = 'gemini';
      row.isDraft = false;
      row.mtMs = translation.latency_ms;
      row.displayedAt = performance.now();
      row.lagMs = performance.now() - (row.receivedAt || performance.now());
      state.lastMt = row.mtMs;
      state.lastLag = row.lagMs;
      row.lateForVideo = state.kind === 'video' && el('demo-video').currentTime > row.mediaEnd + 2.5;
      render();
    }
  } catch (err) {
    console.error('Translation error:', err);
    if (!row.vi) {
      row.status = 'error';
      row.message = err.message;
      error('Đoạn ' + row.id + ': ' + err.message);
    }
  } finally {
    row.isTranslating = false;
    state.translating = Math.max(0, state.translating - 1);

    while (state.mtQueue.length > 0 && state.translating < 2) {
      const nextRow = state.mtQueue.shift();
      triggerRowTranslation(nextRow);
    }

    if (row.en !== row.lastTranslatedEn || row.needsRetranslate) {
      triggerRowTranslation(row);
    } else {
      finishStatus();
      render();
    }
  }
}

async function polishRowWithGemini(row) {
  if (!row || row.session !== state.session || row.isPolished || !row.isFinal) return;
  row.isPolished = true;
  try {
    const context = state.rows.filter(r => r.id < row.id && r.en).slice(-2).map(r => r.en).join(' ').slice(-3000);
    const sourceEpoch = (state.vision && Number.isInteger(state.vision.sourceEpoch)) ? state.vision.sourceEpoch : 0;
    const segStartMs = Math.round((row.startSec || 0) * 1000);
    const segEndMs = Math.round((row.endSec || 0) * 1000);
    const polished = await requestJSON('/api/translate-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: row.en,
        initial_translation: row.vi || '',
        previous_context: context,
        provider: 'gemini',
        model: state.geminiModel || 'gemini-3.5-flash-lite',
        mode: 'stream',
        source_epoch: sourceEpoch,
        segment_audio_start_ms: segStartMs,
        segment_audio_end_ms: segEndMs
      })
    });
    if (row.session !== state.session) return;
    row.vi = polished.translated_text;
    row.isDraft = false;
    row.polishedMs = polished.latency_ms;
    row.provider = 'gemini';

    // Gate Phase 5 & Section 3: If user has already moved to a newer segment (row.id < state.activeRow?.id),
    // update timeline DOM card, but do NOT pull video caption/floating display back to the old row!
    const isPastSegment = Boolean(state.activeRow && row.id < state.activeRow.id);
    if (isPastSegment) {
      renderTimeline();
    } else {
      render();
    }
  } catch (err) {
    console.warn('Gemini polish fallback:', err);
    row.isDraft = false;
    if (state.activeRow && row.id < state.activeRow.id) {
      renderTimeline();
    } else {
      render();
    }
  } finally {
    finishStatus();
  }
}

function finishStatus(){
  if(!state.capturing&&!state.stopping&&!state.processing&&!state.translating&&!state.queue.length&&!state.pendingWords.length&&(!state.activeRow||state.activeRow.isFinal)){
    setSafeText('state', 'Đã dừng thu · xử lý xong');
  }
}

async function processQueue(){
  if(state.processing)return;state.processing=true;
  try{
    while(state.queue.length){
      const job=state.queue.shift();
      if(job.session!==state.session)continue;
      try{
        const asr=await requestJSON('/api/live/asr',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Sample-Rate':'16000'},body:job.pcm.buffer});
        if(job.session!==state.session)continue;
        if(!Array.isArray(asr.words))throw new Error('Server ASR cũ chưa trả timestamp từ. Dừng và mở lại studio.cmd.');
        state.lastAsr=asr.asr_latency_ms;
        if(state.stabilizer.previous.some(w=>w.end<job.startSec)){
          state.dropped++;state.rows.push({id:state.rows.length+1,status:'skipped',startSec:state.stabilizer.previous[0].start,endSec:job.startSec,durationSec:0,en:'',vi:'',message:'ASR không theo kịp: âm thanh chưa chốt đã ra khỏi bộ đệm 12 giây.'});
        }
        const words=asr.words.map(w=>({...w,start:w.start+job.startSec,end:w.end+job.startSec,mediaStart:job.mediaOffset===null?null:w.start+job.startSec+job.mediaOffset,mediaEnd:job.mediaOffset===null?null:w.end+job.startSec+job.mediaOffset,receivedAt:job.receivedAt}));
        const result=state.stabilizer.update(words,job.final);
        state.segmenter?.trimBefore(Math.max(0,state.stabilizer.committedEnd-1.5));
        state.asrDraft=result.draft.map(w=>w.text).join(' ');
        if(result.committed.length){if(!state.pendingWords.length)state.pendingSince=performance.now();state.pendingWords.push(...result.committed);}
        consumePendingWords(job.final);
      }catch(e){error(e.message);}
      render();
    }
  }finally{
    state.processing=false;
    if(!state.capturing&&!state.stopping)consumePendingWords(true);
    finishStatus();
    render();
  }
}
async function sampleAndSendFrame() {
  if (!state.capturing || !state.vision || !state.vision.active || state.vision.enabled === false) return;
  const video = state.vision.videoElement;
  if (!video || video.paused || video.ended || video.seeking) return;
  if (video.readyState !== undefined && video.readyState < 2) return;
  const vw = video.videoWidth || video.width || 0;
  const vh = video.videoHeight || video.height || 0;
  if (vw <= 0 || vh <= 0) return;

  if (state.vision.inFlight) return;
  state.vision.inFlight = true;

  const session = state.session;
  const epoch = state.vision.sourceEpoch;
  const frameId = `f_${++state.vision.frameIdCounter}`;
  const capturedClientMs = performance.now();
  renderSlideInspector();

  try {
    let targetW = vw;
    let targetH = vh;
    const maxDim = Math.max(vw, vh);
    if (maxDim > 1280) {
      const scale = 1280 / maxDim;
      targetW = Math.round(vw * scale);
      targetH = Math.round(vh * scale);
    }

    if (!state.vision.canvas && typeof document !== 'undefined' && document.createElement) {
      state.vision.canvas = document.createElement('canvas');
    }
    const canvas = state.vision.canvas;
    if (!canvas || typeof canvas.getContext !== 'function') {
      state.vision.inFlight = false;
      return;
    }

    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext('2d');
    if (ctx && typeof ctx.drawImage === 'function') {
      ctx.drawImage(video, 0, 0, targetW, targetH);
    }

    const blob = await new Promise(resolve => {
      if (typeof canvas.toBlob === 'function') {
        canvas.toBlob(resolve, 'image/jpeg', 0.85);
      } else {
        resolve(null);
      }
    });

    if (!blob || session !== state.session || !state.vision.active) {
      state.vision.inFlight = false;
      return;
    }

    const resp = await fetch('/api/live/vision/frame', {
      method: 'POST',
      headers: {
        'Content-Type': 'image/jpeg',
        'X-Session-ID': String(session),
        'X-Source-Epoch': String(epoch),
        'X-Frame-ID': frameId,
        'X-Captured-Client-Ms': String(capturedClientMs),
        'X-Stabilization-Delay-Sec': '0.6'
      },
      body: blob
    });

    if (resp.ok && session === state.session && state.vision.active) {
      const data = await resp.json().catch(() => null);
      if (data && data.status) {
        if (data.status === 'stabilizing') {
          state.vision.status = 'STABILIZING';
          renderSlideInspector();
        } else if (data.status === 'queued') {
          state.vision.status = 'OCR_PENDING';
          renderSlideInspector();
        }
      }
    }
  } catch (err) {
    console.warn('Vision frame upload error:', err);
  } finally {
    state.vision.inFlight = false;
  }
}

async function pollVisionResult() {
  if (!state.capturing || !state.vision || !state.vision.active || state.vision.enabled === false) return;
  const session = state.session;
  const epoch = state.vision.sourceEpoch;

  try {
    const resp = await fetch(`/api/live/vision/result?session_id=${encodeURIComponent(session)}&source_epoch=${encodeURIComponent(epoch)}`, {
      method: 'GET',
      headers: {
        'X-Session-ID': String(session),
        'X-Source-Epoch': String(epoch)
      }
    });

    if (!resp.ok) return;
    const snap = await resp.json().catch(() => null);
    if (!snap) return;

    if (session !== state.session || !state.vision.active) return;
    if (snap.source_epoch !== undefined && snap.source_epoch !== epoch) return;

    state.vision.status = snap.status || 'NO_FRAME';

    if (snap.status === 'READY' && snap.slide_id) {
      state.currentSlide = snap;
      if (!state.slides) state.slides = [];
      const existing = state.slides.find(s => s.slide_id === snap.slide_id);
      if (!existing) {
        state.slides.push({
          session_id: String(session),
          source_epoch: epoch,
          slide_id: snap.slide_id,
          slide_revision: snap.slide_revision || 1,
          title: snap.title || '',
          entities: snap.entities || [],
          status: 'READY',
          content_hash: snap.content_hash || '',
          isUserEdited: false,
          firstSeenMs: performance.now()
        });
      } else {
        existing.slide_revision = snap.slide_revision || existing.slide_revision;
        if (!existing.isUserEdited) {
          existing.title = snap.title || existing.title;
          existing.entities = snap.entities || existing.entities;
          existing.content_hash = snap.content_hash || existing.content_hash;
        }
      }
      saveSlidesToStorage();
    }

    renderSlideInspector();
  } catch (err) {
    console.warn('Vision result poll error:', err);
  }
}

function startVisionSchedulers(session) {
  if (state.vision.sampleTimer) clearInterval(state.vision.sampleTimer);
  if (state.vision.pollTimer) clearInterval(state.vision.pollTimer);

  state.vision.sampleTimer = setInterval(() => {
    if (session !== state.session || !state.capturing || !state.vision?.active) return;
    sampleAndSendFrame();
  }, 500);

  state.vision.pollTimer = setInterval(() => {
    if (session !== state.session || !state.capturing || !state.vision?.active) return;
    pollVisionResult();
  }, 1200);
}

function cleanupVision() {
  if (!state.vision) return;
  state.vision.active = false;
  if (state.vision.sampleTimer) {
    clearInterval(state.vision.sampleTimer);
    state.vision.sampleTimer = null;
  }
  if (state.vision.pollTimer) {
    clearInterval(state.vision.pollTimer);
    state.vision.pollTimer = null;
  }
  if (state.vision.hiddenVideo) {
    try {
      state.vision.hiddenVideo.pause();
      state.vision.hiddenVideo.srcObject = null;
      if (state.vision.hiddenVideo.parentNode) {
        state.vision.hiddenVideo.parentNode.removeChild(state.vision.hiddenVideo);
      }
    } catch (e) {}
    state.vision.hiddenVideo = null;
  }
  state.vision.videoElement = null;
  state.vision.inFlight = false;

  const resetSession = String(state.session);
  const resetEpoch = state.vision.sourceEpoch;
  if (typeof fetch === 'function') {
    fetch('/api/live/vision/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: resetSession, source_epoch: resetEpoch })
    }).catch(e => console.warn('Vision reset error:', e));
  }
}

async function startCapture(kind,captureWindow=window){
  if(!state.ready){error('Hệ thống đang khởi động model, vui lòng đợi 1–2 giây rồi bấm lại...');return;}
  if(state.stopping)return;
  if(state.capturing)await stopCapture();
  state.processing=false;state.translating=0;state.mtQueue=[];state.queue.items=[];
  timelineCards.clear();
  error('');const session=++state.session;state.rows=[];state.pair=new LiveAudioCore.TranscriptPair();state.presenter=new LiveAudioCore.CaptionPresenter();state.asrDraft='';state.pendingWords=[];state.history=[];state.dropped=0;state.activeRow=null;state.lastAsr=null;state.lastMt=null;state.lastLag=null;renderVideoCaption();
  state.stabilizer=new LiveAudioCore.StableWords();state.presenter=new LiveAudioCore.CaptionPresenter();state.pair=new LiveAudioCore.TranscriptPair();state.pendingWords=[];state.asrDraft='';state.captionInvalid=false;
  
  if (state.vision) {
    cleanupVision();
  } else {
    state.vision = {
      active: false,
      sessionId: '0',
      sourceEpoch: 0,
      frameIdCounter: 0,
      inFlight: false,
      sampleTimer: null,
      pollTimer: null,
      hiddenVideo: null,
      videoElement: null,
      canvas: null,
      status: 'NO_FRAME'
    };
  }
  state.vision.sourceEpoch = (state.vision.sourceEpoch || 0) + 1;
  state.vision.sessionId = String(session);
  state.vision.status = 'NO_FRAME';
  renderSlideInspector();

  el('share').disabled=true;el('mic').disabled=true;el('demo-start').disabled=true;el('state').textContent='Đang chọn nguồn…';
  let stream,ctx;
  try{
    // Invoke the browser picker directly from the click gesture.
    const mediaPromise=kind==='video'?(async()=>{
      const video=el('demo-video');
      const capture=video.captureStream||video.mozCaptureStream;
      if(!capture)throw new Error('Trình duyệt chưa hỗ trợ captureStream. Hãy mở trang bằng Chrome.');
      if(video.ended)video.currentTime=0;
      await video.play();
      let stream=capture.call(video);
      let retries=6;
      while(!stream.getAudioTracks().length&&retries-->0){
        await new Promise(r=>setTimeout(r,80));
        stream=capture.call(video);
      }
      return stream;
    })():kind==='tab'?((window.navigator&&window.navigator.mediaDevices)||navigator.mediaDevices).getDisplayMedia({video:{displaySurface:'browser'},audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},selfBrowserSurface:'exclude',systemAudio:'include'}):navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    try{ctx=new AudioContext({sampleRate:16000});}catch{ctx=new AudioContext();}
    const resume=ctx.resume();stream=await mediaPromise;await resume;
    if(!stream.getAudioTracks().length)throw new Error(kind==='video'?'Không thu được âm thanh video. Thử bấm lại Phát video NVIDIA.':'Nguồn chia sẻ không có âm thanh. Hãy chọn "Thẻ Chrome" (Chrome Tab) và BẬT tùy chọn "Chia sẻ âm thanh của thẻ" (Share tab audio) ở góc dưới bên trái.');
    await ctx.audioWorklet.addModule('/pcm-worklet.js');
    const source=ctx.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
    const node=new AudioWorkletNode(ctx,'pcm16k',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
    state.stream=stream;state.ctx=ctx;state.node=node;state.sourceNode=source;state.segmenter=new LiveAudioCore.RollingAudio({hopSec:Number(el('chunk').value)/1000});
    state.capturing=true;state.stopping=false;state.kind=kind;

    if (kind === 'tab') {
      const vTracks = stream.getVideoTracks ? stream.getVideoTracks() : [];
      if (vTracks.length > 0) {
        const vTrack = vTracks[0];
        const hiddenVideo = document.createElement('video');
        hiddenVideo.muted = true;
        hiddenVideo.playsInline = true;
        hiddenVideo.style.position = 'fixed';
        hiddenVideo.style.top = '-9999px';
        hiddenVideo.style.left = '-9999px';
        hiddenVideo.style.width = '1px';
        hiddenVideo.style.height = '1px';
        hiddenVideo.style.opacity = '0';
        hiddenVideo.style.pointerEvents = 'none';
        if (typeof hiddenVideo.setAttribute === 'function') {
          hiddenVideo.setAttribute('aria-hidden', 'true');
        }
        if (typeof document !== 'undefined' && document.body && typeof document.body.appendChild === 'function') {
          document.body.appendChild(hiddenVideo);
        }
        if (typeof MediaStream === 'function') {
          hiddenVideo.srcObject = new MediaStream([vTrack]);
        }
        if (typeof hiddenVideo.play === 'function') {
          hiddenVideo.play().catch(e => console.warn('Hidden video play error:', e));
        }
        state.vision.hiddenVideo = hiddenVideo;
        state.vision.videoElement = hiddenVideo;
        state.vision.active = true;
        startVisionSchedulers(session);
      } else {
        state.vision.videoElement = null;
        state.vision.active = false;
        state.vision.status = 'MIC_NO_VIDEO';
      }
    } else if (kind === 'video') {
      state.vision.videoElement = el('demo-video');
      state.vision.hiddenVideo = null;
      state.vision.active = true;
      startVisionSchedulers(session);
    } else {
      state.vision.videoElement = null;
      state.vision.hiddenVideo = null;
      state.vision.active = false;
      state.vision.status = 'MIC_NO_VIDEO';
    }

    node.port.onmessage=e=>{
      if(session!==state.session)return;
      if(e.data.flushed){state.flushResolve?.();return;}
      if(!state.segmenter||!e.data.pcm)return;
      if(kind==='video'&&el('demo-video').paused&&!state.stopping)return;
      const pcm=new Int16Array(e.data.pcm),receivedAt=performance.now();
      enqueue(state.segmenter.push(pcm,e.data.rms,receivedAt));
      el('level').style.width=`${Math.min(100,e.data.rms*500)}%`;
      el('capture-clock').textContent=`Đã thu ${seconds(state.segmenter.total/16000)} giây`;
    };
    source.connect(node);node.connect(ctx.destination); // Worklet outputs zeros, so shared audio is not replayed.
    for(const track of stream.getTracks())track.addEventListener('ended',()=>stopCapture(),{once:true});
    el('source').textContent=kind==='video'?'Nguồn: âm thanh video NVIDIA đang phát':kind==='tab'?`Nguồn: ${stream.getVideoTracks()[0]?.label||'tab đang chia sẻ'}`:'Nguồn: micro · nói tiếng Anh';
    el('state').textContent='Đang thu âm thanh trực tiếp';render();
  }catch(e){
    if(kind==='video')el('demo-video').pause();
    cleanupVision();
    stream?.getTracks().forEach(track=>track.stop());await ctx?.close().catch(()=>{});
    state.capturing=false;state.stream=null;state.ctx=null;state.node=null;state.segmenter=null;
    error(e.name==='NotAllowedError'?'Bạn chưa cấp quyền chia sẻ/thu âm. Bấm lại và chọn nguồn để thử.':e.message);
    el('state').textContent='Chưa bắt đầu thu';render();
  }
}
async function stopCapture(){
  if(!state.stream||state.stopping)return;
  state.stopping=true;state.capturing=false;
  cleanupVision();
  renderSlideInspector();
  el('state').textContent='Đang dừng thu và xử lý đoạn cuối…';render();
  if(state.kind==='video')el('demo-video').pause();
  if(state.activeRow&&!state.activeRow.isFinal){
    state.activeRow.isFinal=true;
    const fin=state.activeRow;state.activeRow=null;
    triggerRowTranslation(fin);
  }
  try{
    state.sourceNode?.disconnect();
    if(state.node){await new Promise(resolve=>{const timeout=setTimeout(resolve,600);state.flushResolve=()=>{clearTimeout(timeout);resolve();};state.node.port.postMessage('flush');});}
    enqueue(state.segmenter?.flush());
    state.stream.getTracks().forEach(track=>track.stop());
    if(state.node){state.node.port.onmessage=null;state.node.disconnect();}
    await state.ctx?.close().catch(()=>{});
  }finally{
    state.flushResolve=null;state.stream=null;state.ctx=null;state.node=null;state.sourceNode=null;state.segmenter=null;state.stopping=false;
    el('level').style.width='0%';el('state').textContent=state.processing||state.queue.length||state.translating||state.mtQueue.length?'Đã dừng thu · đang xử lý hàng đợi':'Đã dừng thu';render();
  }
}
let floatingCssCache = '';

async function openPip(){
  if(state.pip&&!state.pip.closed){state.pip.focus();return;}
  try{
    if('documentPictureInPicture' in window){state.pip=await window.documentPictureInPicture.requestWindow({width:480,height:360});}
    else{state.pip=window.open('','live_subtitles','width=620,height=350');if(!state.pip)throw new Error('Trình duyệt chặn cửa sổ. Cho phép popup hoặc dùng Chrome hỗ trợ PiP.');error('Trình duyệt không hỗ trợ Document PiP; cửa sổ thường không bảo đảm luôn nổi.');}
    const doc=state.pip.document;doc.head.replaceChildren();doc.body.replaceChildren();
    doc.documentElement.lang='vi';doc.title='Phụ đề nổi · Anh → Việt';

    const link=doc.createElement('link');link.rel='stylesheet';link.href='/floating.css';
    const style=doc.createElement('style');
    if(floatingCssCache)style.textContent=floatingCssCache;
    doc.head.append(link,style);
    fetch('/floating.css').then(r=>r.text()).then(t=>{floatingCssCache=t;style.textContent=t;}).catch(()=>{});

    doc.body.innerHTML='<header><strong><span class="live-dot"></span>Phiên dịch trực tiếp · EN → VI</strong><button id="stop" type="button">Dừng thu</button></header><div id="state" role="status"></div><button id="pip-share" type="button">Chọn tab có âm thanh</button><main class="pip-stage"><p id="en"></p><p id="vi"></p><p id="draft-bar" class="draft-bar"></p></main><p id="pip-error" role="alert"></p><footer><button id="return" type="button">Về trang dịch</button></footer>';
    doc.getElementById('stop').onclick=()=>stopCapture();
    doc.getElementById('pip-share').onclick=()=>startCapture('tab');
    doc.getElementById('return').onclick=()=>window.focus();
    const pipWindow=state.pip;
    pipWindow.addEventListener('pagehide',()=>{if(state.pip===pipWindow){state.pip=null;el('pip').textContent='Mở lại phụ đề nổi';el('pip-hint').textContent='Cửa sổ nổi đã đóng. Âm thanh vẫn tiếp tục được xử lý; bấm Mở lại phụ đề nổi để xem.';}},{once:true});
    el('pip').textContent='Đưa phụ đề nổi lên trước';
    el('pip-hint').textContent='Chọn tab có âm thanh trong cửa sổ nổi và bật Chia sẻ âm thanh tab. Có thể kéo cửa sổ tới góc màn hình, đổi kích thước hoặc cỡ chữ.';
    render();
  }catch(e){error(e.message);}
}
el('share').onclick=()=>startCapture('tab');el('mic').onclick=()=>startCapture('mic');el('stop').onclick=()=>stopCapture();el('pip').onclick=()=>openPip();
el('engine-mode')?.addEventListener('change',e=>{
  state.engineMode=e.target.value;
  state.model=(state.engineMode==='local'?state.localModel:state.geminiModel);
  render();
});
el('demo-start').onclick=async()=>{
  const video=el('demo-video');
  if(video.ended)video.currentTime=0;
  if(state.capturing&&state.kind==='video'){
    if(video.paused)await video.play().catch(e=>error('Không phát được video: '+e.message));
    return;
  }
  startCapture('video');
};
el('video-fullscreen').onclick=async()=>{
  try{
    if(document.fullscreenElement)await document.exitFullscreen();
    else await el('video-stage').requestFullscreen();
  }catch(e){error('Không mở được toàn màn hình: '+e.message);}
};
setInterval(()=>{
  renderVideoCaption();
  if(state.activeRow&&!state.activeRow.isFinal){
    const ageMs=performance.now()-(state.activeRow.updatedAt||0);
    if(LiveAudioCore.phraseReady(state.activeRow.words,false,ageMs)){
      state.activeRow.isFinal=true;
      const fin=state.activeRow;state.activeRow=null;
      triggerRowTranslation(fin);
    }
  }
  if(state.pendingWords.length&&(performance.now()-state.pendingSince>=400)){
    consumePendingWords(false);
  }
},250);
el('demo-video').addEventListener('ended',()=>{if(state.kind==='video')stopCapture();});
el('demo-video').addEventListener('play',()=>{if(state.ready&&!state.capturing&&!state.stopping)startCapture('video');});
// Demo video pause does NOT stop capture to allow inspection & human editing without data loss
el('demo-video').addEventListener('seeking',()=>{
  if(state.kind==='video'){
    state.captionInvalid=true;
    renderVideoCaption();
    if(state.vision){
      state.vision.sourceEpoch=(state.vision.sourceEpoch||0)+1;
    }
    if(state.capturing){
      stopCapture();
      error('Đã tua video. Chờ xử lý xong rồi bấm Phát video NVIDIA và dịch để bắt đầu phiên mới tại vị trí này.');
    }
  }
});
el('export').onclick=()=>{
  const content={
    version:2,
    exportedAt:new Date().toISOString(),
    model:state.model,
    asrHopMs:Number(el('chunk').value),
    asrWindowSec:12,
    dropped:state.dropped,
    latencyDefinition:'client receipt of ASR snapshot final PCM packet to translation result; not utterance-end latency',
    ocrEnabled:!!(state.vision?.active||(state.slides && state.slides.length > 0)||state.currentSlide),
    totalSlides:state.slides ? state.slides.length : 0,
    currentSlide:state.currentSlide||null,
    slides:state.slides||[],
    segments:state.rows
  };
  const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='live-session-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener('pagehide',()=>{state.stream?.getTracks().forEach(track=>track.stop());state.ctx?.close();state.pip?.close();});

if (typeof globalThis !== 'undefined') {
  globalThis.LiveVision = {
    sampleAndSendFrame,
    pollVisionResult,
    renderSlideInspector,
    renderSlideChips,
    initSlideNavButtons,
    cleanupVision,
    renderEntityTags,
    initSlideToggle,
    saveSlidesToStorage,
    loadSlidesFromStorage
  };
}

function updateCaptionPreferences() {
  const captionsEl = el('video-captions');
  const showEn = !!el('caption-show-en')?.checked;
  const size = el('caption-font-size')?.value || 'medium';
  if (captionsEl) {
    if (typeof captionsEl.classList?.toggle === 'function') {
      captionsEl.classList.toggle('show-en', showEn);
    }
    if (typeof captionsEl.setAttribute === 'function') {
      captionsEl.setAttribute('data-size', size);
    }
  }
}

(async()=>{
  try{
    loadSlidesFromStorage();
    initSlideToggle();
    initSlideNavButtons();
    initOcrModal();
    renderSlideInspector();
    el('caption-show-en')?.addEventListener('change', updateCaptionPreferences);
    el('caption-font-size')?.addEventListener('change', updateCaptionPreferences);
    updateCaptionPreferences();
    if(!navigator.mediaDevices||!window.AudioWorkletNode)throw new Error('Cần trình duyệt hỗ trợ thu âm và AudioWorklet; mở bằng Chrome trên localhost.');
    const info=await requestJSON('/api/translation-status');
    if(!info.live_audio_enabled)throw new Error('Server đang chạy bản cũ. Nhấn Ctrl+C ở cửa sổ server rồi mở lại studio.cmd.');
    if(!info.incremental_asr_enabled)throw new Error('Cần khởi động lại server để bật ASR tăng dần: Ctrl+C rồi mở studio.cmd.');
    if(!info.configured)throw new Error('Server chưa cấu hình provider/khóa dịch. Chạy studio.cmd để dùng local hoặc studio.cmd gemini để nhập khóa.');
    state.localModel = info.local_model || 'facebook/nllb-200-distilled-600M';
    state.geminiModel = info.gemini_model || (info.provider === 'gemini' ? (info.model || 'gemini-3.5-flash-lite') : 'gemini-3.5-flash-lite');
    state.model = (state.engineMode === 'local' ? state.localModel : state.geminiModel);
    el('config').textContent=`Provider: ${info.provider} · Model: ${info.model||'text demo'} · ASR local · OCR slide sẵn sàng`;
    el('state').textContent='Đang khởi động ASR local…';render();
    try{await requestJSON('/api/live/warmup',{method:'POST'});}catch(wErr){console.warn('Warmup non-blocking:',wErr);}
    state.ready=true;el('state').textContent='Sẵn sàng phát video hoặc chia sẻ tab';render();
  }catch(e){error(e.message);el('state').textContent='Chưa sẵn sàng: '+e.message;render();}
})();
