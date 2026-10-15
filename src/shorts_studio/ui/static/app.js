(() => {
  const $ = (id) => document.getElementById(id);
  const state = { inputMode: "url", uploadToken: "", jobId: "", pollTimer: 0, busy: false, aiReady: false, scriptAIReady: false, ttsReady: false, oauthReady: false, coupangReady: false, finalReady: false, productId: "", productCandidates: [], uploadEdited: { title: false, description: false, tags: false } };
  const el = {
    url: $("source-url"), file: $("source-file"), output: $("output-path"), mode: $("frame-mode"),
    start: $("start-button"), cancel: $("cancel-button"), taskTitle: $("task-status-title"),
    taskDetail: $("task-status-detail"), statusDot: $("status-dot"), progressWrap: $("task-progress-wrap"),
    progress: $("task-progress"), progressLabel: $("task-progress-label"), sourceBadge: $("source-badge"),
    removeBadge: $("remove-badge"), previewBadge: $("preview-badge"), readiness: $("readiness-warning"),
  };
  const show = (node) => node.classList.remove("hidden");
  const hide = (node) => node.classList.add("hidden");
  const setText = (node, text) => { node.textContent = text == null ? "" : String(text); };
  const errorMessage = (data) => data && data.error ? data.error : "요청을 처리하지 못했습니다.";

  async function api(path, options = {}) {
    const response = await fetch(path, { cache: "no-store", ...options });
    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await response.json() : {};
    if (!response.ok) throw new Error(errorMessage(data));
    return data;
  }

  function setInputMode(mode) {
    state.inputMode = mode;
    state.uploadToken = "";
    $("url-tab").classList.toggle("selected", mode === "url");
    $("file-tab").classList.toggle("selected", mode === "file");
    $("url-tab").setAttribute("aria-selected", String(mode === "url"));
    $("file-tab").setAttribute("aria-selected", String(mode === "file"));
    $("url-panel").classList.toggle("hidden", mode !== "url");
    $("file-panel").classList.toggle("hidden", mode !== "file");
    updateStartButton();
  }

  function hasSource() {
    return state.inputMode === "url" ? Boolean(el.url.value.trim()) : Boolean(state.uploadToken);
  }

  function updateStartButton() {
    el.start.disabled = state.busy || !hasSource();
    if (state.busy) setText(el.start, "처리 중…");
    else if (state.jobId) setText(el.start, "새 작업 준비");
    else setText(el.start, "문자 제거 시작");
  }

  function setTask(title, detail, kind = "ready") {
    setText(el.taskTitle, title);
    setText(el.taskDetail, detail);
    el.statusDot.className = `status-dot ${kind === "busy" ? "busy" : kind === "error" ? "error" : ""}`;
  }

  function badge(node, text, kind = "muted") {
    setText(node, text);
    node.className = `badge badge-${kind}`;
  }

  function setBusy(value) {
    state.busy = value;
    updateStartButton();
    updateStageButtons();
    if (value) {
      const stage = $("task-status-title").textContent;
      if (/분석|대본|합성|YouTube 업로드/.test(stage)) hide(el.cancel); else show(el.cancel);
      show(el.progressWrap);
    } else {
      hide(el.cancel);
      hide(el.progressWrap);
    }
  }

  async function loadReadiness() {
    try {
      const { readiness } = await api("/api/status");
      const removal = readiness.text_removal;
      if (!removal.ready) {
        show(el.readiness);
        setText(el.readiness, `${removal.label}: ${removal.detail || ""}`);
        badge(el.removeBadge, "준비 필요", "warning");
      } else {
        hide(el.readiness);
        badge(el.removeBadge, "필수 처리 사용 가능", "success");
      }
      const settings = await api("/api/settings");
      state.aiReady = settings.ai.provider !== "disabled" && settings.ai.key_saved;
      state.scriptAIReady = settings.script_ai.provider === "gemini" && settings.script_ai.key_saved;
      state.ttsReady = settings.tts.provider === "windows-local" && settings.tts.ready;
      state.oauthReady = Boolean(settings.youtube_oauth_saved);
      state.coupangReady = Boolean(settings.coupang && settings.coupang.credentials_saved);
      setText($("oauth-status"), state.oauthReady ? "OAuth client 설정 저장됨" : "OAuth 설정 필요");
      if (!state.coupangReady && !$("script-editor").value.trim()) badge($("product-badge"), "Partners API 설정 필요", "muted");
      updateStageButtons();
      return readiness;
    } catch (error) {
      show(el.readiness);
      setText(el.readiness, error.message);
      return null;
    }
  }

  function updateStageButtons() {
    const hasCleanVideo = Boolean(state.jobId);
    $("analyze-button").disabled = state.busy || !hasCleanVideo || !state.aiReady;
    $("script-button").disabled = state.busy || !$("analysis-editor").value.trim() || !state.scriptAIReady;
    $("render-button").disabled = state.busy || !$("script-editor").value.trim() || !state.ttsReady;
    $("voice-preview-button").disabled = state.busy || !$("script-editor").value.trim() || !state.ttsReady;
    $("product-search-button").disabled = state.busy || !$("script-editor").value.trim() || !state.coupangReady;
    $("product-search-button").title = state.coupangReady ? "대본 키워드로 Coupang 후보를 최대 10개 검색합니다." : "설정에서 승인된 Coupang Partners Access/Secret Key를 등록하세요.";
    $("upload-button").disabled = state.busy || !state.finalReady || !state.oauthReady || !$("upload-title").value.trim();
    $("analyze-button").title = state.aiReady ? "선택한 Gemini 모델로 분석합니다." : "설정에서 Gemini API Key를 등록하세요.";
    $("script-button").title = state.scriptAIReady ? "Gemini API로 한국어 대본을 생성합니다." : "설정에서 Gemini API Key를 등록하고 연결을 확인하세요.";
    $("render-button").title = state.ttsReady ? "Windows Heami 로컬 음성과 자막을 합성합니다." : "MSIX 설치와 Windows 한국어 Heami 음성 설치를 확인하세요.";
  }

  function uploadFile(file) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024 * 1024) {
      setTask("업로드할 수 없습니다", "파일 크기는 2 GB 이하여야 합니다.", "error");
      return;
    }
    state.uploadToken = "";
    show($("upload-progress-wrap"));
    $("upload-progress").style.width = "0%";
    setText($("upload-label"), "업로드 준비 중…");
    setText($("file-label"), file.name);
    el.file.disabled = true;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const amount = Math.round(event.loaded / event.total * 100);
        $("upload-progress").style.width = `${amount}%`;
        setText($("upload-label"), `원본 업로드 ${amount}% · ${formatBytes(event.loaded)} / ${formatBytes(event.total)}`);
      }
    };
    xhr.onload = () => {
      el.file.disabled = false;
      let result = {};
      try { result = JSON.parse(xhr.responseText); } catch (_) { /* API error below */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        hide($("upload-progress-wrap"));
        setTask("업로드 실패", result.error || "파일을 업로드하지 못했습니다.", "error");
        return;
      }
      state.uploadToken = result.token;
      setText($("upload-label"), `업로드 완료 · ${formatBytes(result.size)}`);
      setText($("artifact-source"), result.name);
      setText($("artifact-source-state"), "준비됨");
      badge(el.sourceBadge, "파일 준비됨", "success");
      setTask("영상 준비됨", "설정을 확인하고 문자 제거를 시작하세요.");
      updateStartButton();
    };
    xhr.onerror = () => {
      el.file.disabled = false;
      hide($("upload-progress-wrap"));
      setTask("업로드 실패", "로컬 앱에 연결할 수 없습니다.", "error");
    };
    setTask("영상 업로드 중", "업로드가 끝나면 작업을 시작할 수 있습니다.", "busy");
    xhr.send(file);
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes, unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
    return `${value.toFixed(unit > 0 ? 1 : 0)} ${units[unit]}`;
  }

  async function startJob() {
    if (state.jobId && !state.busy) resetJob();
    const source = state.inputMode === "url" ? el.url.value.trim() : state.uploadToken;
    if (!source) return;
    const output = el.output.value.trim();
    setBusy(true);
    setTask("작업을 시작합니다", "입력 영상과 문자 제거 모델을 확인합니다.", "busy");
    badge(el.sourceBadge, "작업 중", "warning");
    badge(el.removeBadge, "대기 중", "muted");
    try {
      const job = await api("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, output, mode: el.mode.value }) });
      state.jobId = job.id;
      $("analysis-editor").value = ""; $("script-editor").value = "";
      updateStageButtons();
      setText($("artifact-source"), job.source_name);
      setText($("artifact-source-state"), job.is_url ? "다운로드 대기" : "등록됨");
      badge(el.sourceBadge, "처리 중", "warning");
      state.pollTimer = window.setInterval(pollJob, 1000);
      pollJob();
    } catch (error) {
      setBusy(false);
      badge(el.sourceBadge, "확인 필요", "error");
      setTask("작업을 시작하지 못했습니다", error.message, "error");
    }
  }

  async function pollJob() {
    if (!state.jobId) return;
    try {
      const { job } = await api("/api/status");
      if (!job || job.id !== state.jobId) return;
      setText(el.taskTitle, job.status === "completed" ? "문자 제거 완료" : job.status_text || "처리 중");
      setText(el.taskDetail, job.stage === "text_removal" ? "전체 화면에서 문자를 탐지하고 복원하고 있습니다." : job.source_name || "");
      const percent = Math.round(Math.max(0, Math.min(1, Number(job.progress) || 0)) * 100);
      el.progress.style.width = `${percent}%`;
      setText(el.progressLabel, job.stage === "text_removal"
        ? `전체 진행률 ${percent}% · 문자 탐지 및 영상 복원 중`
        : `${percent}% · ${job.status_text || "처리 중"}`);
      if (job.stage === "text_removal") badge(el.removeBadge, "문자 제거 중", "warning");
      if (job.stage === "analyze") badge($("analysis-badge"), "분석 중", "warning");
      if (job.stage === "script") badge($("script-badge"), "대본 생성 중", "warning");
      if (job.stage === "render") badge($("script-badge"), "음성·자막 합성 중", "warning");
      if (job.status === "completed" && job.stage === "completed") renderCompleted(job);
      else if (job.status === "completed" && job.stage.endsWith("_completed")) renderActionCompleted(job);
      else if (job.status === "failed" || job.status === "cancelled") renderStopped(job);
    } catch (error) {
      setTask("상태를 가져오지 못했습니다", error.message, "error");
    }
  }

  function renderCompleted(job) {
    clearInterval(state.pollTimer);
    setBusy(false);
    badge(el.sourceBadge, "완료", "success");
    badge(el.removeBadge, "검토 필요", "warning");
    badge(el.previewBadge, "재생 가능", "success");
    setTask("문자 제거 완료", "결과 영상을 재생하고 대표 프레임의 복원 품질을 확인하세요.");
    hide($("empty-preview"));
    const video = $("result-video");
    video.src = job.video_url;
    show(video);
    const link = $("download-link");
    link.href = job.video_url;
    link.download = job.output ? job.output.split(/[\\/]/).pop() : "shorts.mp4";
    show(link);
    setText($("artifact-clean"), job.output || "문자 제거 결과 MP4");
    setText($("artifact-clean-state"), "완료");
    setText($("artifact-report-state"), job.report && Object.keys(job.report).length ? "생성됨" : "없음");
    const report = job.report || {};
    const stats = $("report-stats");
    stats.replaceChildren();
    const entries = [["탐지 프레임", report.frames_with_text ?? "—"], ["전체 프레임", report.frames ?? "—"], ["복원 방식", report.method_description || report.method || "검토 리포트"]];
    for (const [label, value] of entries) {
      const chip = document.createElement("span");
      chip.className = "stat-chip";
      const strong = document.createElement("b");
      strong.textContent = value;
      chip.append(strong, document.createTextNode(label));
      stats.append(chip);
    }
    show(stats);
    if (job.preview_url) {
      $("preview-image").src = job.preview_url;
      show($("preview-image-wrap"));
      $("compare-image").src = job.preview_url;
      show($("compare-button"));
    }
    const details = $("video-details");
    details.replaceChildren();
    for (const [label, value] of [["FORMAT", "MP4"], ["FRAME", "9:16"], ["AUDIO", "제거됨"]]) {
      const item = document.createElement("div");
      const small = document.createElement("small"); small.textContent = label;
      const strong = document.createElement("b"); strong.textContent = value;
      item.append(small, strong); details.append(item);
    }
    show(details);
    $("artifact-report-state").className = "artifact-state";
    document.querySelector('[data-step="source"]').classList.add("done");
    document.querySelector('[data-step="remove"]').classList.add("done");
    if (job.analysis) $("analysis-editor").value = JSON.stringify(job.analysis, null, 2);
    if (job.script) { $("script-editor").value = JSON.stringify(job.script, null, 2); fillUploadDraft(job.script); }
    badge($("analysis-badge"), job.analysis ? "분석 완료" : "Provider 연결 후 실행", job.analysis ? "success" : "muted");
    badge($("script-badge"), job.script ? "대본 준비됨" : "분석 후 생성", job.script ? "success" : "muted");
    updateStageButtons();
  }

  function renderActionCompleted(job) {
    clearInterval(state.pollTimer); setBusy(false);
    setTask(job.status_text || "단계 완료", "결과를 확인하고 다음 제작 단계를 선택하세요.");
    if (job.analysis) {
      $("analysis-editor").value = JSON.stringify(job.analysis, null, 2);
      badge($("analysis-badge"), "분석 완료", "success");
      document.querySelector('[data-step="script"]').classList.add("done");
    }
    if (job.script) {
      $("script-editor").value = JSON.stringify(job.script, null, 2);
      badge($("script-badge"), "대본 준비됨", "success");
      const keywords = job.script.product_keywords || [];
      if (keywords.length && !$("product-keyword").value) $("product-keyword").value = keywords[0];
      fillUploadDraft(job.script);
      badge($("product-badge"), "검색할 수 있습니다", "success");
      document.querySelector('[data-step="voice"]').classList.add("active");
      if (keywords.length && !state.productId && state.coupangReady) searchProducts();
      else if (!state.coupangReady) badge($("product-badge"), "Partners API 설정 필요", "warning");
    }
    if (job.final_video_url) {
      state.finalReady = true;
      const video = $("final-video"); video.src = job.final_video_url; show(video); show($("final-video-label"));
      const base = `/api/jobs/${job.id}`;
      for (const [id, kind, filename] of [["final-download-link", "final", "final.mp4"], ["srt-download-link", "srt", "captions.srt"], ["voice-download-link", "voice", "voice.wav"], ["report-download-link", "narration-report", "narration.json"]]) {
        const link = $(id); link.href = `${base}/${kind}`; link.download = filename;
      }
      show($("final-downloads"));
      setText($("artifact-final-state"), "완료");
      setText($("artifact-sidecars-state"), "생성됨");
      setText($("artifact-final"), job.final_output || "최종 영상 MP4");
      badge(el.previewBadge, "최종 영상 재생 가능", "success");
      document.querySelector('[data-step="voice"]').classList.add("done");
    }
    if (job.upload_receipt) {
      const receipt = $("upload-receipt"); receipt.replaceChildren();
      const link = document.createElement("a"); link.href = job.upload_receipt.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = job.upload_receipt.url;
      receipt.append(document.createTextNode(`업로드 완료 · ${job.upload_receipt.privacy_status} · `), link); show(receipt);
      badge($("upload-badge"), "업로드 완료", "success");
      document.querySelector('[data-step="export"]').classList.add("done");
    }
    updateStageButtons();
  }

  async function runStageAction(action, payload = {}) {
    if (!state.jobId || state.busy) return;
    setTask(({ analyze: "AI 영상 분석 중", script: "한국어 대본 생성 중", render: "음성·자막 합성 중", upload: "YouTube 업로드 중" })[action], "작업 결과를 같은 화면에 저장합니다.", "busy");
    setBusy(true);
    try {
      await api(`/api/jobs/${state.jobId}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      state.pollTimer = window.setInterval(pollJob, 1000);
      pollJob();
    } catch (error) {
      setBusy(false); setTask("단계를 시작하지 못했습니다", error.message, "error");
    }
  }

  function parseEditor(id, description) {
    try { return JSON.parse($(id).value); }
    catch (_) { throw new Error(`${description} JSON 형식을 확인하세요.`); }
  }

  async function searchProducts() {
    const keyword = $("product-keyword").value.trim();
    if (!keyword) { setTask("검색어가 필요합니다", "상품 이름이나 대본의 product keyword를 입력하세요.", "error"); return; }
    const button = $("product-search-button"); button.disabled = true; button.textContent = "검색 중…";
    try {
      const { products } = await api("/api/products/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keyword }) });
      state.productCandidates = products;
      const list = $("product-results"); list.replaceChildren();
      if (products.length) {
        const note = document.createElement("p"); note.className = "product-data-note";
        note.textContent = "최대 10개 검색 후보입니다. 판매량·리뷰 수는 Partners API 응답에 포함된 경우만 표시하고, 미제공 값은 임의로 채우지 않습니다.";
        list.append(note);
      }
      if (!products.length) { const empty = document.createElement("p"); empty.className = "stage-summary"; empty.textContent = "검색 후보가 없습니다."; list.append(empty); }
      for (const product of products) {
        const card = document.createElement("div"); card.className = "product-result"; card.dataset.productId = product.id;
        if (product.id === state.productId) card.classList.add("selected");
        const info = document.createElement("div");
        if (product.image_url && /^https:\/\//i.test(product.image_url)) {
          const image = document.createElement("img"); image.src = product.image_url; image.alt = ""; image.loading = "lazy"; image.referrerPolicy = "no-referrer"; image.className = "product-image"; info.append(image);
        }
        const text = document.createElement("div"); text.className = "product-result-info";
        const productUrl = product.affiliate_url || product.url;
        const link = document.createElement("a"); link.href = /^https:\/\//i.test(productUrl) ? productUrl : "#"; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = product.title;
        const detail = document.createElement("small"); detail.textContent = `${product.price == null ? "가격 미표시" : `${Number(product.price).toLocaleString("ko-KR")}원`} · 검색 순위 ${product.rank || "—"} · 관련도 ${Math.round(product.score * 100)}%`;
        const stats = document.createElement("small"); stats.className = "product-stats";
        const sales = product.sales_count == null ? "API 미제공" : `${Number(product.sales_count).toLocaleString("ko-KR")}건`;
        const reviews = product.review_count == null ? "API 미제공" : `${Number(product.review_count).toLocaleString("ko-KR")}건`;
        stats.textContent = `판매량 ${sales} · 리뷰 ${reviews}${product.rating == null ? "" : ` · 평점 ${Number(product.rating).toFixed(1)}`}`;
        const shipping = document.createElement("small");
        const badges = [product.is_rocket === true ? "로켓배송" : "", product.is_free_shipping === true ? "무료배송" : ""].filter(Boolean);
        shipping.textContent = badges.join(" · ") || `일치 검색어: ${(product.matched_terms || []).join(", ") || "검색 결과"}`;
        text.append(link, detail, stats, shipping); info.append(text);
        const select = document.createElement("button"); select.type = "button"; select.className = "button button-secondary"; select.textContent = product.id === state.productId ? "선택됨" : "이 상품 선택";
        select.disabled = product.id === state.productId;
        select.addEventListener("click", () => selectProduct(product.id));
        card.append(info, select); list.append(card);
      }
      badge($("product-badge"), `${products.length}개 후보`, products.length ? "success" : "muted");
      try {
        const script = parseEditor("script-editor", "대본");
        fillUploadDraft(script, script.product || null);
      } catch (_) { /* Keep search results visible even if the draft is being edited. */ }
      setTask("상품 검색 완료", "상위 후보 링크를 설명란에 넣었습니다. 영상과 같은 상품을 선택해 주세요.");
    } catch (error) { setTask("상품 검색 실패", error.message, "error"); }
    finally { button.textContent = "후보 검색"; updateStageButtons(); }
  }

  async function selectProduct(productId) {
    try {
      const { script } = await api(`/api/jobs/${state.jobId}/product`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ product_id: productId }) });
      $("script-editor").value = JSON.stringify(script, null, 2);
      state.productId = productId;
      fillUploadDraft(script, script.product);
      for (const card of $("product-results").querySelectorAll(".product-result")) {
        const button = card.querySelector("button");
        const selected = card.dataset.productId === productId;
        card.classList.toggle("selected", selected);
        button.textContent = selected ? "선택됨" : "이 상품 선택";
        button.disabled = selected;
      }
      badge($("product-badge"), "대본에 연결됨", "success");
      setTask("상품과 게시 문안을 준비했습니다", "상품 링크·제휴 고지를 포함해 제목, 설명, 태그를 채웠습니다. 공개 전 내용을 확인하세요.");
    } catch (error) { setTask("상품을 연결하지 못했습니다", error.message, "error"); }
  }

  function fillUploadDraft(script, product = null) {
    if (!script || typeof script !== "object") return;
    const narration = (script.segments || []).map((segment) => segment.narration || "").filter(Boolean).join("\n");
    const parts = [script.hook || "", narration, script.cta || ""].filter(Boolean);
    const candidates = [...state.productCandidates];
    if (product && !candidates.some((item) => item.id === product.id)) candidates.unshift(product);
    const links = candidates.slice(0, 10).map((item, index) => {
      const url = item.affiliate_url || item.url;
      return /^https:\/\//i.test(url || "") ? `${index + 1}. ${item.title}\n${url}` : "";
    }).filter(Boolean);
    if (links.length) {
      parts.push("상품 정보 및 링크 (관련도순)");
      parts.push(links.join("\n\n"));
      parts.push("쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받을 수 있습니다.");
    }
    const description = parts.join("\n\n").slice(0, 5000);
    const rawTags = [...(script.product_keywords || []), product && product.title, "쇼츠", "shorts", ...(product ? ["쿠팡파트너스"] : [])];
    const tags = [...new Set(rawTags.map((tag) => String(tag || "").trim()).filter(Boolean))].join(", ").slice(0, 500);
    if (!state.uploadEdited.title) $("upload-title").value = String(script.title || "").trim().slice(0, 100);
    if (!state.uploadEdited.description) $("upload-description").value = description;
    if (!state.uploadEdited.tags) $("upload-tags").value = tags;
    setText($("upload-draft-status"), links.length ? `자동 작성 완료 · 상품 후보 ${links.length}개 링크와 제휴 고지를 설명란에 넣었습니다. 영상의 마지막 음성과 자막에도 설명란 안내가 포함됩니다.` : "자동 작성 완료 · 상품 검색 후 최대 10개 링크와 제휴 고지를 설명란에 추가합니다. 영상 마지막에는 상품 정보를 설명란에서 확인하도록 안내합니다.");
    updateStageButtons();
  }

  async function saveOAuthClient() {
    const file = $("youtube-oauth-file").files[0];
    if (!file) { setTask("OAuth 파일이 필요합니다", "Google Cloud에서 받은 Desktop OAuth client JSON을 선택하세요.", "error"); return; }
    if (file.size > 256 * 1024) { setTask("OAuth 파일이 너무 큽니다", "JSON 파일은 256 KB 이하여야 합니다.", "error"); return; }
    try {
      const oauth_json = await file.text();
      await api("/api/settings/youtube-oauth", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ oauth_json }) });
      state.oauthReady = true; setText($("oauth-status"), "OAuth client 설정 저장됨");
      setTask("YouTube OAuth 설정 완료", "최종 영상을 비공개 기본값으로 업로드할 수 있습니다."); updateStageButtons();
    } catch (error) { setTask("OAuth 설정을 저장하지 못했습니다", error.message, "error"); }
  }

  function uploadToYouTube() {
    const privacy = $("upload-privacy").value;
    if (privacy === "public" && !window.confirm("이 영상이 YouTube에 공개 게시됩니다. 계속할까요?")) return;
    const tags = $("upload-tags").value.split(",").map((tag) => tag.trim()).filter(Boolean);
    runStageAction("upload", { title: $("upload-title").value.trim(), description: $("upload-description").value,
      tags, privacy_status: privacy, allow_public: privacy === "public" });
  }

  function renderStopped(job) {
    clearInterval(state.pollTimer);
    setBusy(false);
    const failed = job.status === "failed";
    badge(el.sourceBadge, failed ? "실패" : "취소됨", failed ? "error" : "muted");
    badge(el.removeBadge, failed ? "실패" : "취소됨", failed ? "error" : "muted");
    setTask(failed ? "작업 실패" : "작업 취소됨", job.error || job.status_text, failed ? "error" : "ready");
    if (failed) {
      show(el.readiness);
      setText(el.readiness, job.error || "오류 내용을 확인하세요.");
    }
  }

  async function cancelJob() {
    el.cancel.disabled = true;
    try { await api("/api/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); setTask("작업을 취소합니다", "진행 중인 변환 프로세스를 정리하고 있습니다.", "busy"); }
    catch (error) { setTask("취소할 수 없습니다", error.message, "error"); }
    finally { el.cancel.disabled = false; }
  }

  function resetJob() {
    clearInterval(state.pollTimer);
    state.jobId = "";
    setBusy(false);
    hide($("result-video"));
    $("result-video").removeAttribute("src");
    hide($("download-link")); hide($("preview-image-wrap")); hide($("compare-button")); hide($("report-stats")); hide($("video-details"));
    show($("empty-preview"));
    setText($("artifact-clean"), "필수 단계 완료 후 생성");
    setText($("artifact-clean-state"), "대기");
    setText($("artifact-report-state"), "대기");
    badge(el.removeBadge, "대기 중", "muted");
    badge(el.previewBadge, "결과 대기", "muted");
    badge(el.sourceBadge, state.inputMode === "file" && state.uploadToken ? "파일 준비됨" : "입력 대기", state.uploadToken ? "success" : "muted");
    setTask("준비됨", "URL을 입력하거나 영상 파일을 선택하세요.");
    $("analysis-editor").value = ""; $("script-editor").value = ""; hide($("final-video")); hide($("final-video-label")); hide($("upload-receipt")); state.finalReady = false;
    state.productId = ""; state.productCandidates = []; state.uploadEdited = { title: false, description: false, tags: false };
    $("product-keyword").value = ""; $("product-results").replaceChildren();
    $("upload-title").value = ""; $("upload-description").value = ""; $("upload-tags").value = ""; $("upload-privacy").value = "private";
    setText($("upload-draft-status"), "대본 생성 후 제목·설명·태그를 자동 작성합니다. 상품 선택 시 링크와 제휴 고지가 추가됩니다.");
    setText($("artifact-final"), "대본·TTS 단계 완료 후 생성"); setText($("artifact-final-state"), "대기"); setText($("artifact-sidecars-state"), "대기"); hide($("final-downloads"));
    badge($("analysis-badge"), "대기 중", "muted"); badge($("script-badge"), "대기 중", "muted");
    updateStageButtons();
    updateStartButton();
  }

  const GEMINI_MODEL_FALLBACK = [
    { id: "gemini-3.8-flash", label: "Gemini 3.8 Flash · 권장" },
    { id: "gemini-3.6-flash", label: "Gemini 3.6 Flash" },
    { id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite · 무료·경량" },
    { id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite · 경량 처리" },
  ];
  const settingForms = {
    script_ai: { title: "Gemini AI 분석 · 한국어 대본", fields: [["model", "사용할 Gemini 모델", "model"], ["secret", "Gemini API Key", "password"]] },
    tts: { title: "한국어 TTS · 무료 로컬", fields: [["provider", "TTS 방식", "select", ["windows-local", "disabled"]], ["voice", "Windows 음성", "voice"]] },
    youtube: { title: "YouTube 검색", fields: [["key_name", "API key 환경 변수 이름"], ["secret", "YouTube API key · 비워두면 기존 키 유지", "password"]] },
    tiktok: { title: "TikTok Commercial API", fields: [["client_key_name", "Client key 환경 변수 이름"], ["client_secret_name", "Client secret 환경 변수 이름"], ["client_key", "Client key · 기존 값 유지 시 비움", "password"], ["client_secret", "Client secret · 기존 값 유지 시 비움", "password"]] },
    coupang: { title: "Coupang Partners", fields: [["access_key", "Access Key", "password"], ["secret_key", "Secret Key", "password"]] },
    updates: { title: "업데이트", fields: [["repository", "GitHub 저장소 (owner/repo)"], ["public_key", "Ed25519 공개키 (base64)"]] },
    resources: { title: "성능·자원 사용", fields: [["cpu_threads", "문자 제거 최대 CPU thread", "select"], ["background_priority", "다른 앱 우선 (낮은 프로세스 우선순위)", "select", [
      { value: true, label: "사용 · PC 반응성 우선" }, { value: false, label: "사용 안 함 · 기본 우선순위" },
    ]]] },
  };
  const settingDefaults = {
    script_ai: { model: "gemini-3.8-flash" },
    tts: { provider: "windows-local", voice: "Microsoft Heami Desktop - Korean" },
    youtube: { key_name: "SHORTS_YOUTUBE_API_KEY" },
    tiktok: { client_key_name: "SHORTS_TIKTOK_CLIENT_KEY", client_secret_name: "SHORTS_TIKTOK_CLIENT_SECRET" },
    resources: { cpu_threads: 2, background_priority: true },
  };
  const settingGuides = {
    tts: [
      "비용: Windows에 포함된 음성을 로컬에서 사용하므로 TTS API Key나 외부 TTS 호출이 없습니다.",
      "필수 조건: MSIX 설치본으로 실행하고, Windows 음성 설정에 한국어 Heami 음성이 설치되어 있어야 합니다.",
      "음성이 준비되지 않으면 상태를 새로고침한 뒤 다시 확인하세요. Windows 설정 > 시간 및 언어 > 음성에서 음성을 추가할 수 있습니다.",
    ],
    script_ai: [
      "이 Gemini 모델 하나를 STEP 03 영상 분석과 한국어 대본 생성에 함께 사용합니다.",
      "Google AI Studio에서 발급한 Gemini API Key를 입력하세요. 같은 Key는 두 기능이 공유하며 Windows Credential Manager에 보관됩니다.",
      "무료 사용은 모델별 quota와 요청 제한이 적용됩니다. 무료 tier에서는 전송한 내용이 Google 제품 개선에 사용될 수 있습니다. 무료 한도·데이터 정책을 확인해 주세요.",
      "연결 확인은 Gemini API 테스트 요청을 1회 보냅니다. 영상 장면 분석은 영상에서 추출한 frame 이미지를 Gemini로 전송합니다.",
    ],
    youtube: [
      "용도: YouTube 영상 후보 검색용 Data API Key입니다. YouTube 업로드 OAuth 설정과는 다른 인증입니다.",
      "Google Cloud 프로젝트에서 YouTube Data API v3를 활성화하고 API Key를 발급해 입력하세요.",
      "검색 기능을 쓰지 않으면 설정할 필요가 없습니다. Key 이름은 기본값을 그대로 두면 됩니다.",
    ],
    tiktok: [
      "용도: 승인된 TikTok Commercial Content API의 광고 참고 검색입니다. 일반 TikTok 영상 검색 Key가 아닙니다.",
      "TikTok 개발자 앱에서 발급받은 Client Key와 Client Secret을 입력하세요. 승인 전이면 비워두세요.",
      "Key 이름은 기본값을 그대로 둘 수 있습니다. 비밀 값은 Windows Credential Manager에 저장됩니다.",
    ],
    coupang: [
      "용도: Coupang Partners 상품 후보 검색입니다. 판매자 WING Open API Key와는 다릅니다.",
      "파트너스 계정의 API 사용 최종 승인과 Partners Access Key/Secret Key 발급 후 입력하세요.",
      "아직 계정이나 Key가 없으면 설정하지 않아도 됩니다. 검색에는 시간당 최대 10회 제한이 있습니다.",
    ],
    updates: [
      "GitHub 저장소는 owner/repo 형식으로 입력하세요.",
      "공개키는 Release manifest 검증에 사용합니다. 설치 배포용 signing key와 한 쌍인 Base64 Ed25519 public key를 입력하세요.",
      "업데이트 기능을 구성하지 않으면 비워둘 수 있습니다.",
    ],
    resources: [
      "CPU thread 상한은 문자 탐지·복원과 영상 변환·인코딩에 사용할 수 있는 최대 논리 CPU 수입니다. 장치에서 사용 가능한 수만큼 선택할 수 있습니다.",
      "thread를 줄이면 처리 시간이 길어집니다. 다른 앱 반응성을 우선하려면 1~2개 또는 사용 가능 수의 절반 이하로 시작하세요.",
      "‘다른 앱 우선’을 켜면 Windows에서 처리 프로세스 우선순위를 낮춰 작업 중 PC 반응성을 높입니다.",
    ],
  };
  let settingsSnapshot = {};
  let selectedSettingsTab = "script_ai";

  function renderSettingsTab(name) {
    selectedSettingsTab = name;
    const tabs = $("settings-tabs"); tabs.replaceChildren();
    for (const [key, config] of Object.entries(settingForms)) {
      const tab = document.createElement("button"); tab.type = "button";
      tab.className = `settings-tab ${key === name ? "selected" : ""}`; tab.textContent = config.title;
      tab.addEventListener("click", () => renderSettingsTab(key)); tabs.append(tab);
    }
    const config = settingForms[name], values = settingsSnapshot[name] || {};
    const content = $("settings-content"); content.replaceChildren();
    const form = document.createElement("div"); form.className = "settings-form-grid";
    for (const [key, label, type = "text", options] of config.fields) {
      const wrap = document.createElement("div"); wrap.className = "field";
      const fieldLabel = document.createElement("label"); fieldLabel.textContent = label; fieldLabel.htmlFor = `setting-${name}-${key}`;
      let input;
      if (type === "model") {
        input = document.createElement("input"); input.type = "hidden";
        input.id = `setting-${name}-${key}`; input.dataset.settingKey = key;
        input.value = values[key] ?? settingDefaults[name]?.[key] ?? "";
        const picker = document.createElement("div"); picker.className = "model-picker";
        picker.setAttribute("role", "group"); picker.setAttribute("aria-label", label);
        const hint = document.createElement("small"); hint.className = "model-picker-hint";
        hint.textContent = "사용할 모델을 선택한 뒤 ‘이 설정 저장’을 눌러주세요.";
        const modelOptions = Array.isArray(values.models) && values.models.length
          ? values.models : GEMINI_MODEL_FALLBACK;
        const choices = modelOptions.map((item) => ({ value: item.id, label: item.label }));
        for (const choice of choices) {
          const option = document.createElement("button"); option.type = "button";
          option.className = `model-option ${choice.value === input.value ? "selected" : ""}`;
          option.textContent = choice.label; option.setAttribute("aria-pressed", String(choice.value === input.value));
          option.addEventListener("click", () => {
            input.value = choice.value;
            picker.querySelectorAll(".model-option").forEach((item) => {
              const selected = item === option;
              item.classList.toggle("selected", selected); item.setAttribute("aria-pressed", String(selected));
            });
          });
          picker.append(option);
        }
        wrap.append(fieldLabel, picker, hint, input); form.append(wrap); continue;
      } else if (type === "select" || type === "voice") {
        input = document.createElement("select");
        const choices = (name === "resources" && key === "cpu_threads"
          ? Array.from({ length: Number(values.available_threads) || 1 }, (_, index) => ({ value: index + 1, label: `${index + 1} thread${index ? "s" : ""}` }))
          : options) || (name === "script_ai" ? (values.models || []).map((item) => ({ value: item.id, label: item.label })) :
          name === "tts" ? (values.voice_options?.length ? values.voice_options : [settingDefaults.tts.voice]).map((item) => ({ value: item, label: item })) : []);
        for (const choice of choices) {
          const option = document.createElement("option");
          option.value = typeof choice === "string" ? choice : choice.value;
          option.textContent = typeof choice === "string" ? choice : choice.label;
          input.append(option);
        }
      } else { input = document.createElement("input"); input.type = type; }
      input.id = `setting-${name}-${key}`; input.dataset.settingKey = key;
      if (type === "number") { input.min = "0.25"; input.max = "4"; input.step = "0.05"; }
      if (type === "password") input.placeholder = values[`${key}_saved`] || (key === "secret" && values.key_saved) ? "Credential Manager에 저장됨 · 교체 시 입력" : "저장할 값 입력";
      else input.value = values[key] ?? settingDefaults[name]?.[key] ?? "";
      wrap.append(fieldLabel, input); form.append(wrap);
    }
    content.append(form);
    const note = document.createElement("p"); note.className = "settings-note";
    note.textContent = name === "script_ai" ? `Gemini 전용 설정 · ${values.key_saved ? "API Key 저장됨" : "API Key 미설정"} · Key는 Windows Credential Manager에 저장됩니다.` :
      name === "coupang" ? "파트너스 API credentials는 Windows Credential Manager에 저장됩니다." :
      name === "youtube" ? "API Key는 Windows Credential Manager에 저장됩니다." :
      name === "tts" ? (values.ready ? `무료 로컬 TTS 사용 가능 · ${values.voice}` : `TTS 준비 필요 · ${values.detail || "MSIX 및 Heami 음성 상태를 확인하세요."}`) :
      name === "tiktok" ? "비밀 값은 설정 파일에 저장하지 않고 Windows Credential Manager에서 불러옵니다." :
      name === "resources" ? `현재 설정: 최대 ${values.cpu_threads || 2} / ${values.available_threads || 1} threads · 문자 제거 시작 시 적용됩니다.` :
      "설정 값은 사용자 PC의 로컬 설정 파일에서 관리합니다.";
    content.append(note);
    if (name === "resources") {
      const warning = document.createElement("p"); warning.className = "settings-resource-warning";
      warning.setAttribute("role", "note");
      warning.textContent = `주의: 사용 가능한 ${values.available_threads || 1}개 논리 thread 중 선택한 수까지 사용할 수 있습니다. 전체에 가깝게 설정하면 PC 반응이 느려질 수 있습니다. 버벅임을 줄이려면 1~2개 또는 절반 이하부터 시작하세요. 이는 RAM이나 CPU 사용률을 정확한 퍼센트로 제한하지 않습니다.`;
      content.append(warning);
    }
    const guide = document.createElement("section"); guide.className = "settings-guide";
    const guideTitle = document.createElement("h3"); guideTitle.textContent = "입력 가이드"; guide.append(guideTitle);
    const guideList = document.createElement("ul");
    for (const item of settingGuides[name] || []) { const row = document.createElement("li"); row.textContent = item; guideList.append(row); }
    guide.append(guideList); content.append(guide);
    if (name === "script_ai") {
      const link = document.createElement("a"); link.href = "https://aistudio.google.com/app/apikey";
      link.target = "_blank"; link.rel = "noopener noreferrer"; link.className = "settings-help-link";
      link.textContent = "Google AI Studio에서 API Key 만들기"; content.append(link);
    }
    const actions = document.createElement("div"); actions.className = "settings-form-actions";
    const save = document.createElement("button"); save.type = "button"; save.className = "button button-primary"; save.textContent = "이 설정 저장";
    save.addEventListener("click", () => saveSettings(name, form, save)); actions.append(save); content.append(actions);
    if (name === "script_ai") {
      const test = document.createElement("button"); test.type = "button"; test.className = "button button-secondary";
      test.textContent = "저장 후 Gemini 연결 확인";
      test.addEventListener("click", () => saveAndTestGemini(form, test)); actions.append(test);
    }
    $("settings-message").classList.add("hidden");
  }

  async function saveSettings(name, form, button) {
    const body = {};
    form.querySelectorAll("[data-setting-key]").forEach((input) => { body[input.dataset.settingKey] = input.value.trim(); });
    if (name === "tts" && body.speed) body.speed = Number(body.speed);
    button.disabled = true;
    try {
      const settingName = name === "script_ai" ? "script-ai" : name;
      const result = await api(`/api/settings/${settingName}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      settingsSnapshot = result.settings; renderSettingsTab(name);
      const message = $("settings-message"); message.className = "inline-warning"; setText(message, "설정을 저장했습니다.");
      setTask("설정 저장 완료", `${settingForms[name].title} 설정을 저장했습니다.`); await loadReadiness();
      if (name === "coupang" && state.coupangReady && $("script-editor").value.trim() && !state.productId) searchProducts();
    } catch (error) {
      const message = $("settings-message"); message.className = "inline-warning"; setText(message, error.message);
    } finally { button.disabled = false; }
  }

  async function saveAndTestGemini(form, button) {
    const body = {};
    form.querySelectorAll("[data-setting-key]").forEach((input) => { body[input.dataset.settingKey] = input.value.trim(); });
    button.disabled = true;
    try {
      const saved = await api("/api/settings/script-ai", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      settingsSnapshot = saved.settings;
      const result = await api("/api/settings/script-ai/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const message = $("settings-message"); message.className = "inline-warning"; setText(message, `${result.message} (${result.model})`);
      setTask("Gemini 연결 성공", `${result.model}로 한국어 대본 생성을 사용할 수 있습니다.`);
      await loadReadiness();
    } catch (error) {
      const message = $("settings-message"); message.className = "inline-warning"; setText(message, error.message);
    } finally { button.disabled = false; }
  }

  async function openSettings() {
    try { settingsSnapshot = await api("/api/settings"); }
    catch (error) { settingsSnapshot = {}; setTask("설정을 불러오지 못했습니다", error.message, "error"); }
    renderSettingsTab(selectedSettingsTab); $("settings-dialog").showModal();
  }

  async function openHistory() {
    const list = $("history-list"); list.replaceChildren();
    try {
      const { jobs } = await api("/api/history");
      if (!jobs.length) {
        const empty = document.createElement("p"); empty.className = "modal-copy"; empty.textContent = "저장된 작업 기록이 없습니다."; list.append(empty);
      }
      for (const job of jobs) {
        const row = document.createElement("div"); row.className = "history-item";
        const info = document.createElement("span");
        const title = document.createElement("b"); title.textContent = job.source || "영상 작업";
        const meta = document.createElement("small"); meta.textContent = `${job.stage || job.status} · ${job.updated_at || ""}`;
        info.append(title, meta);
        const badge = document.createElement("span"); badge.className = "history-state"; badge.textContent = job.status || "기록";
        row.append(info, badge); list.append(row);
      }
    } catch (error) { setTask("작업 기록을 열지 못했습니다", error.message, "error"); }
    $("history-dialog").showModal();
  }

  $("url-tab").addEventListener("click", () => setInputMode("url"));
  $("file-tab").addEventListener("click", () => setInputMode("file"));
  el.url.addEventListener("input", () => { badge(el.sourceBadge, el.url.value.trim() ? "URL 입력됨" : "입력 대기", el.url.value.trim() ? "success" : "muted"); updateStartButton(); });
  el.file.addEventListener("change", () => uploadFile(el.file.files[0]));
  $("dropzone").addEventListener("dragover", (event) => { event.preventDefault(); $("dropzone").classList.add("drag-over"); });
  $("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("drag-over"));
  $("dropzone").addEventListener("drop", (event) => { event.preventDefault(); $("dropzone").classList.remove("drag-over"); setInputMode("file"); uploadFile(event.dataTransfer.files[0]); });
  el.start.addEventListener("click", startJob);
  el.cancel.addEventListener("click", cancelJob);
  $("new-job").addEventListener("click", resetJob);
  $("settings-button").addEventListener("click", openSettings);
  $("help-button").addEventListener("click", () => $("help-dialog").showModal());
  $("history-button").addEventListener("click", openHistory);
  $("close-button").addEventListener("click", async () => {
    if (state.busy && !window.confirm("작업을 취소하고 Shorts Studio를 종료할까요?")) return;
    if (state.busy) { try { await api("/api/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); } catch (_) { /* stop local server below */ } }
    try { await api("/api/shutdown", { method: "POST" }); } catch (_) { /* the server closes this connection */ }
    setTask("앱이 종료되었습니다", "이 브라우저 탭을 닫아도 됩니다.");
  });
  $("analyze-button").addEventListener("click", () => runStageAction("analyze"));
  $("script-button").addEventListener("click", () => {
    try { runStageAction("script", { analysis: parseEditor("analysis-editor", "분석"), duration_sec: Number($("script-duration").value), tone: $("script-tone").value, call_to_action: $("script-cta").value.trim() }); }
    catch (error) { setTask("대본을 생성하지 못했습니다", error.message, "error"); }
  });
  $("render-button").addEventListener("click", () => {
    try { runStageAction("render", { script: parseEditor("script-editor", "대본") }); }
    catch (error) { setTask("음성을 합성하지 못했습니다", error.message, "error"); }
  });
  let voicePreviewUrl = "";
  $("voice-preview-button").addEventListener("click", async () => {
    const button = $("voice-preview-button"); button.disabled = true;
    try {
      const script = parseEditor("script-editor", "대본");
      const response = await fetch("/api/voice-preview", { method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ script }) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(errorMessage(data));
      }
      if (voicePreviewUrl) URL.revokeObjectURL(voicePreviewUrl);
      voicePreviewUrl = URL.createObjectURL(await response.blob());
      const audio = $("voice-preview-audio"); audio.src = voicePreviewUrl; show(audio);
      await audio.play();
      setTask("대본 음성 미리듣기", "설정된 Windows 로컬 음성으로 대본 전체를 합성했습니다.");
    } catch (error) { setTask("음성 미리듣기 실패", error.message, "error"); }
    finally { button.disabled = state.busy || !state.ttsReady || !$("script-editor").value.trim(); }
  });
  $("product-search-button").addEventListener("click", searchProducts);
  $("oauth-upload-button").addEventListener("click", saveOAuthClient);
  $("upload-button").addEventListener("click", uploadToYouTube);
  $("upload-title").addEventListener("input", () => { state.uploadEdited.title = true; updateStageButtons(); });
  $("upload-description").addEventListener("input", () => { state.uploadEdited.description = true; updateStageButtons(); });
  $("upload-tags").addEventListener("input", () => { state.uploadEdited.tags = true; updateStageButtons(); });
  $("analysis-editor").addEventListener("input", updateStageButtons);
  $("script-editor").addEventListener("input", updateStageButtons);
  $("compare-button").addEventListener("click", () => $("compare-dialog").showModal());
  const stepTargets = {
    source: ".source-card",
    remove: "#remove-card",
    script: "#analysis-card",
    voice: "#render-button",
    export: "#product-card",
  };
  document.querySelectorAll("[data-step]").forEach((step) => step.addEventListener("click", () => {
    const selector = stepTargets[step.dataset.step];
    const target = selector ? document.querySelector(selector) : null;
    if (!target) return;
    document.querySelectorAll("[data-step]").forEach((item) => {
      const selected = item === step;
      item.classList.toggle("active", selected);
      if (selected) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    target.scrollIntoView({ behavior, block: "center" });
  }));

  loadReadiness();
})();
