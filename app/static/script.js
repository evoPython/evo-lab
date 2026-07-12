/* ============================================================
   EVO.PYTHON — personal server homepage
   Vanilla JS only. One view is focused at a time; switching
   views is the main animated moment on the page.
   ============================================================ */

(() => {
  'use strict';

  const VIEWS = ['home', 'about', 'projects', 'server', 'music', 'letter', 'links'];
  let currentView = 'home';

  /* ------------------------------------------------------------
     ROUTER — swaps the active tabpanel, moves the sidebar
     indicator, replays the stagger-in animation, syncs the
     URL hash, and starts/stops view-specific behavior.
     ------------------------------------------------------------ */
  function goToView(view, { pushHistory = true } = {}) {
    if (!VIEWS.includes(view)) return;
    const prevPanel = document.getElementById(`panel-${currentView}`);
    const nextPanel = document.getElementById(`panel-${view}`);
    if (!nextPanel) return;

    // Tabs (sidebar)
    document.querySelectorAll('.sidenav__item').forEach((tab) => {
      const isActive = tab.dataset.view === view;
      tab.setAttribute('aria-selected', String(isActive));
      tab.tabIndex = isActive ? 0 : -1;
    });
    moveSidenavIndicator(view);

    // Tabs (mobile bar)
    document.querySelectorAll('.tabbar button').forEach((btn) => {
      btn.setAttribute('aria-current', String(btn.dataset.view === view));
    });

    // Panels — CSS handles the actual crossfade via .is-active;
    // `inert` just keeps hidden panels out of tab order / AT.
    if (prevPanel && prevPanel !== nextPanel) {
      prevPanel.classList.remove('is-active');
      prevPanel.setAttribute('inert', '');
    }
    // force reflow so the stagger animation restarts even if this
    // view was already visited before
    void nextPanel.offsetWidth;
    nextPanel.removeAttribute('inert');
    nextPanel.classList.add('is-active');
    restartStagger(nextPanel);

    // Server metrics only tick while that view is on screen
    if (view === 'server') startMetrics(); else stopMetrics();

    // Scroll the stage to the top for the new view
    const stage = document.getElementById('stage');
    if (stage) stage.scrollTo({ top: 0, behavior: 'auto' });

    if (pushHistory) history.replaceState(null, '', `#${view}`);
    currentView = view;
  }

  function restartStagger(panel) {
    const items = panel.querySelectorAll('.stagger-item');
    items.forEach((el, i) => {
      el.style.animation = 'none';
      void el.offsetWidth;
      el.style.animation = '';
      el.style.animationDelay = `${i * 45}ms`;
    });
  }

  function moveSidenavIndicator(view) {
    const indicator = document.getElementById('sidenavIndicator');
    const target = document.querySelector(`.sidenav__item[data-view="${view}"]`);
    if (!indicator || !target) return;
    indicator.style.transform = `translateY(${target.offsetTop - 18}px)`;
  }

  /* ------------------------------------------------------------
     NAV WIRING — sidebar tabs, mobile tabs, "glance" cards,
     roving-tabindex keyboard support (ARIA tabs pattern)
     ------------------------------------------------------------ */
  function initNav() {
    const tabs = Array.from(document.querySelectorAll('.sidenav__item'));

    tabs.forEach((tab) => {
      tab.addEventListener('click', () => goToView(tab.dataset.view));
    });

    document.getElementById('sidenav')?.addEventListener('keydown', (e) => {
      const idx = tabs.findIndex((t) => t.dataset.view === currentView);
      let nextIdx = null;
      if (e.key === 'ArrowDown') nextIdx = Math.min(tabs.length - 1, idx + 1);
      if (e.key === 'ArrowUp') nextIdx = Math.max(0, idx - 1);
      if (e.key === 'Home') nextIdx = 0;
      if (e.key === 'End') nextIdx = tabs.length - 1;
      if (nextIdx === null) return;
      e.preventDefault();
      const nextTab = tabs[nextIdx];
      goToView(nextTab.dataset.view);
      nextTab.focus();
    });

    document.querySelectorAll('.tabbar button').forEach((btn) => {
      btn.addEventListener('click', () => goToView(btn.dataset.view));
    });

    document.querySelectorAll('[data-goto]').forEach((btn) => {
      btn.addEventListener('click', () => goToView(btn.dataset.goto));
    });

    // number keys 0-6 jump straight to a view (skip while typing)
    document.addEventListener('keydown', (e) => {
      if (!/^[0-6]$/.test(e.key)) return;
      if (isTypingTarget(e.target)) return;
      const view = VIEWS[Number(e.key)];
      if (view) goToView(view);
    });

    // support deep links / back-forward
    window.addEventListener('hashchange', () => {
      const view = location.hash.replace('#', '');
      if (VIEWS.includes(view)) goToView(view, { pushHistory: false });
    });

    const initial = location.hash.replace('#', '');
    if (VIEWS.includes(initial)) {
      goToView(initial, { pushHistory: false });
    } else {
      moveSidenavIndicator('home');
    }

    window.addEventListener('resize', () => moveSidenavIndicator(currentView));
  }

  function isTypingTarget(el) {
    const tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable;
  }

  /* ------------------------------------------------------------
     HERO — a single typed line, once, on load
     ------------------------------------------------------------ */
  function typeHero() {
    const el = document.getElementById('heroTyped');
    if (!el) return;
    const text = 'whoami';
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) { el.textContent = text; return; }
    let i = 0;
    const tick = () => {
      el.textContent = text.slice(0, i);
      i++;
      if (i <= text.length) setTimeout(tick, 70);
    };
    tick();
  }

  /* ------------------------------------------------------------
     PROJECTS — file list + preview pane
     ------------------------------------------------------------ */
  const PROJECTS = {
    'evo-lab': {
      name: 'evo-lab/',
      tag: 'web',
      desc: 'A personal homelab run 24/7 on a 6 year old laptop.', 
      links: ['source', 'readme'],
    },
    'carwash-pos': {
      name: 'carwash-pos/',
      tag: 'web',
      desc: 'A Point of Sale system for a carwash based in Cebu City.', 
      links: ['source', 'demo'],
    },
    'riffmd': {
      name: 'riffmd/',
      tag: 'cli',
      desc: 'Rich Interface For Fetching Music Downloads. A terminal music downloader and player powered by Rich and yt-dlp.',
      links: [''],
    },
    'vault': {
      name: 'vault/',
      tag: 'writing',
      desc: 'Personal collection of notes organized with Zettelkasten in mind.',
      links: [''],
    },
  };

  function initProjects() {
    const list = document.getElementById('fileList');
    const preview = document.getElementById('filePreview');
    if (!list || !preview) return;

    const items = Array.from(list.querySelectorAll('.filelist__item'));

    function render(key) {
      const p = PROJECTS[key];
      preview.setAttribute('data-swap', '');
      preview.innerHTML = `
        <div class="filepreview__name mono">${p.name}</div>
        <p class="filepreview__desc">${p.desc}</p>
        <div class="filepreview__links">
          ${p.links.map((l) => `<a href="#" data-fake-link>${l}</a>`).join('')}
        </div>
      `;
      wireFakeLinks(preview);
    }

    items.forEach((item) => {
      item.addEventListener('click', () => {
        items.forEach((i) => {
          i.classList.remove('is-selected');
          i.setAttribute('aria-selected', 'false');
        });
        item.classList.add('is-selected');
        item.setAttribute('aria-selected', 'true');
        render(item.dataset.project);
      });
    });

    list.addEventListener('keydown', (e) => {
      const idx = items.findIndex((i) => i.classList.contains('is-selected'));
      let nextIdx = null;
      if (e.key === 'ArrowDown') nextIdx = Math.min(items.length - 1, idx + 1);
      if (e.key === 'ArrowUp') nextIdx = Math.max(0, idx - 1);
      if (nextIdx === null) return;
      e.preventDefault();
      items[nextIdx].click();
      items[nextIdx].focus();
    });

    render('evo-lab'); // initial preview
  }

  /* ------------------------------------------------------------
     SERVER — real metrics, polled only while this view is visible
     ------------------------------------------------------------ */
  let metricsTimer = null;
  let cpuGraphBuilt = false;
  const CPU_HISTORY_LEN = 28;
  const cpuHistory = [];

  function formatRate(bps) {
    if (bps == null) return '-- b/s';
    if (bps < 1024) return `${bps.toFixed(0)} b/s`;
    if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} kb/s`;
    return `${(bps / (1024 * 1024)).toFixed(2)} mb/s`;
  }

  function levelClass(val) {
    if (val == null) return '';
    if (val >= 85) return 'is-danger';
    if (val >= 60) return 'is-warn';
    return '';
  }

  function setLevel(el, val) {
    if (!el) return;
    el.classList.remove('is-warn', 'is-danger');
    const cls = levelClass(val);
    if (cls) el.classList.add(cls);
  }

  function buildCpuGraph() {
    const graph = document.getElementById('cpuGraph');
    if (!graph || cpuGraphBuilt) return;
    graph.innerHTML = '';
    for (let i = 0; i < CPU_HISTORY_LEN; i++) {
      const bar = document.createElement('span');
      bar.className = 'syscell__graph-bar';
      graph.appendChild(bar);
    }
    cpuGraphBuilt = true;
  }

  function renderCpuGraph() {
    const graph = document.getElementById('cpuGraph');
    if (!graph) return;
    buildCpuGraph();
    const bars = graph.children;
    const offset = CPU_HISTORY_LEN - cpuHistory.length;
    for (let i = 0; i < bars.length; i++) {
      const bar = bars[i];
      const val = cpuHistory[i - offset];
      if (val == null) {
        bar.style.height = '4%';
        bar.classList.remove('is-warn', 'is-danger');
        continue;
      }
      bar.style.height = Math.max(val, 4) + '%';
      setLevel(bar, val);
    }
  }

  async function fetchMetrics() {
    const uptimeEl = document.getElementById('uptimeVal');
    const procEl = document.getElementById('procVal');
    const loadEl = document.getElementById('loadVal');
    const ramSubEl = document.getElementById('ramSub');
    const diskSubEl = document.getElementById('diskSub');
    const netSentEl = document.getElementById('netSent');
    const netRecvEl = document.getElementById('netRecv');

    try {
      const res = await fetch('/dashboard/api/public-stats');
      if (!res.ok) return;
      const data = await res.json();

      // CPU: big number + rolling sparkline
      const cpuVal = Math.round(data.cpu);
      const cpuValEl = document.querySelector('[data-val="cpu"]');
      if (cpuValEl) {
        cpuValEl.textContent = cpuVal + '%';
        setLevel(cpuValEl, cpuVal);
      }
      cpuHistory.push(cpuVal);
      if (cpuHistory.length > CPU_HISTORY_LEN) cpuHistory.shift();
      renderCpuGraph();

      if (loadEl && data.load) {
        loadEl.textContent = `${data.load['1m']} · ${data.load['5m']} · ${data.load['15m']}`;
      } else if (loadEl) {
        loadEl.textContent = 'n/a';
      }

      // RAM + swap, stacked bars in one card
      ['ram', 'swap'].forEach((key) => {
        const val = Math.round(data[key]);
        const fill = document.querySelector(`[data-fill="${key}"]`);
        const valEl = document.querySelector(`[data-val="${key}"]`);
        if (fill) { fill.style.width = val + '%'; setLevel(fill, val); }
        if (valEl) { valEl.textContent = val + '%'; }
      });
      if (ramSubEl) ramSubEl.textContent = `${data.ram_used_gb} / ${data.ram_total_gb} gb`;

      // Disk
      const diskVal = Math.round(data.disk);
      const diskFill = document.querySelector('[data-fill="disk"]');
      const diskValEl = document.querySelector('[data-val="disk"]');
      if (diskFill) { diskFill.style.width = diskVal + '%'; setLevel(diskFill, diskVal); }
      if (diskValEl) { diskValEl.textContent = diskVal + '%'; setLevel(diskValEl, diskVal); }
      if (diskSubEl) diskSubEl.textContent = `${data.disk_used_gb} / ${data.disk_total_gb} gb`;

      // Network throughput — auto-scaled unit so small traffic (like
      // this very polling request) still reads as something other
      // than a flat "0.00 mb/s"
      if (netSentEl) netSentEl.textContent = formatRate(data.net_sent_bps);
      if (netRecvEl) netRecvEl.textContent = formatRate(data.net_recv_bps);

      if (uptimeEl && data.uptime) uptimeEl.textContent = `uptime ${data.uptime}`;
      if (procEl && data.processes) procEl.textContent = `${data.processes} proc`;
    } catch (err) {
      // server unreachable — just leave the last known values on screen
    }
  }

  function startMetrics() {
    if (metricsTimer) return;
    fetchMetrics();
    metricsTimer = setInterval(fetchMetrics, 3000);
  }

  function stopMetrics() {
    clearInterval(metricsTimer);
    metricsTimer = null;
  }

  /* ------------------------------------------------------------
     CLOCK
     ------------------------------------------------------------ */
  function initClock() {
    const clockEl = document.getElementById('clock');
    const greetEl = document.getElementById('greet');
    if (!clockEl && !greetEl) return;
    const greetings = [
      [5, 11, "good morning!"],
      [11, 17, "good afternoon."],
      [17, 21, "good evening."],
      [21, 24, "up late too?"],
      [0, 3, "what are you doing up so late?"],
      [3, 5, "you need to sleep."],
    ];
    const update = () => {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, '0');
      const mm = String(now.getMinutes()).padStart(2, '0');
      if (clockEl) clockEl.textContent = `${hh}:${mm} local`;
      if (greetEl) {
        const h = now.getHours();
        const match = greetings.find(([start, end]) => h >= start && h < end);
        greetEl.textContent = match ? match[2] : '';
      }
    };
    update();
    setInterval(update, 15000);
  }

  /* ------------------------------------------------------------
     LETTER — a tiny editor, not a corporate form
     ------------------------------------------------------------ */
  const GLITCH_CHARS = '!@#$%^&*<>[]{}/\\|_-=+~?01'.split('');

  function initLetter() {
    const body = document.getElementById('letterBody');
    const from = document.getElementById('letterFrom');
    const field = document.getElementById('editorField');
    const glitch = document.getElementById('editorGlitch');
    const glitchFrom = document.getElementById('editorGlitchFrom');
    const mode = document.getElementById('editorMode');
    const pos = document.getElementById('editorPos');
    const count = document.getElementById('editorCount');
    const dot = document.getElementById('editorDot');
    const sendBtn = document.getElementById('sendLetter');
    const confirm = document.getElementById('editorConfirm');
    const confirmText = document.getElementById('editorConfirmText');
    const statNum = document.getElementById('letterStatNum');
    if (!body) return;

    let currentTotal = null;

    /* ---- statusline: word count + row:col, vim-flavored ---- */
    function updateCount() {
      const words = body.value.trim() ? body.value.trim().split(/\s+/).length : 0;
      count.textContent = `${words} word${words === 1 ? '' : 's'}`;
    }

    function updatePos() {
      const value = body.value;
      const idx = body.selectionStart;
      const upTo = value.slice(0, idx);
      const row = upTo.split('\n').length;
      const col = idx - upTo.lastIndexOf('\n');
      pos.textContent = `${row}:${col}`;
    }

    function setMode(state) {
      // state: 'normal' | 'insert' | 'sending' | 'sent'
      mode.dataset.mode = state;
      mode.textContent = state.toUpperCase();
    }

    /* ---- status line message: fades the old message out, then fades
       the new one in while sliding up from below, instead of an
       instant text swap ---- */
    let statusTimer = null;
    function setStatus(text, colorVar) {
      clearTimeout(statusTimer);
      const swap = () => {
        confirmText.textContent = text || '';
        confirmText.style.color = colorVar || '';
        if (!text) { confirmText.classList.remove('is-entering', 'is-leaving'); return; }
        confirmText.classList.add('is-entering');
        confirmText.classList.remove('is-leaving');
        // force layout so the entering state (translated + transparent)
        // is committed before we transition it back to rest
        void confirmText.offsetWidth;
        requestAnimationFrame(() => confirmText.classList.remove('is-entering'));
      };
      if (!confirmText.textContent.trim()) { swap(); return; }
      confirmText.classList.add('is-leaving');
      statusTimer = setTimeout(swap, 220);
    }

    function markDirty() {
      const hasContent = body.value.trim() || from.value.trim();
      dot.classList.toggle('is-dirty', Boolean(hasContent));
      dot.classList.remove('is-sent', 'is-sending');
      sendBtn.disabled = false;
      clearTimeout(statusTimer);
      confirmText.classList.remove('is-entering', 'is-leaving');
      confirmText.textContent = '';
    }

    body.addEventListener('input', () => { updateCount(); updatePos(); markDirty(); });
    body.addEventListener('click', updatePos);
    body.addEventListener('keyup', updatePos);
    from.addEventListener('input', markDirty);
    body.addEventListener('focus', () => setMode('insert'));
    body.addEventListener('blur', () => { if (mode.dataset.mode === 'insert') setMode('normal'); });

    /* ---- live "letters received" counter, animated on load ---- */
    function animateCount(el, fromVal, toVal, duration = 900) {
      const startTime = performance.now();
      const diff = toVal - fromVal;
      if (diff === 0) { el.textContent = toVal.toLocaleString(); return; }
      el.classList.add('is-bumping');
      function tick(now) {
        const t = Math.min(1, (now - startTime) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        el.textContent = Math.round(fromVal + diff * eased).toLocaleString();
        if (t < 1) {
          requestAnimationFrame(tick);
        } else {
          el.textContent = toVal.toLocaleString();
          setTimeout(() => el.classList.remove('is-bumping'), 300);
        }
      }
      requestAnimationFrame(tick);
    }

    async function loadInitialCount() {
      try {
        const res = await fetch('/letters/count');
        const data = await res.json().catch(() => ({}));
        if (typeof data.total === 'number') {
          currentTotal = data.total;
          animateCount(statNum, 0, currentTotal, 1100);
        } else {
          statNum.textContent = '—';
        }
      } catch (err) {
        statNum.textContent = '—';
      }
    }

    /* ---- device info: same handful of values any analytics script
       would see (platform/language/screen/timezone), self-reported by
       the browser, sent along only when a letter is actually sent ---- */
    function collectDeviceInfo() {
      let screenInfo = '';
      try { screenInfo = `${screen.width}x${screen.height}`; } catch (err) { /* ignore */ }
      let timezone = '';
      try { timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (err) { /* ignore */ }
      return {
        platform: navigator.platform || '',
        language: navigator.language || '',
        screen: screenInfo,
        timezone,
      };
    }

    /* ---- the send animation: characters scramble and fade in a wave
       that sweeps right-to-left within each line, with each line
       (top line first — flip LINE_DIRECTION to -1 for bottom-first)
       starting a little after the one before it. The "from" field, if
       filled in, is treated as the topmost line and animates too. The
       whole thing runs slower the longer the letter is. ---- */
    const LINE_DIRECTION = 1; // 1 = top-to-bottom stagger, -1 = bottom-to-top

    function buildGlitchSpans(container, text) {
      container.innerHTML = '';
      if (!text) return { spans: [], lineCount: 0 };
      const lines = text.split('\n');
      const spans = [];
      lines.forEach((line, li) => {
        let col = 0;
        for (const ch of line) {
          const span = document.createElement('span');
          span.className = 'editor__glitch-char';
          span.textContent = ch;
          span.dataset.orig = ch;
          span.dataset.col = col;
          span.dataset.line = li;
          container.appendChild(span);
          spans.push(span);
          col++;
        }
        if (li < lines.length - 1) container.appendChild(document.createElement('br'));
      });
      return { spans, lineCount: lines.length };
    }

    /* ---- as the erase wave moves through the lines, slowly scroll
       the overlay to follow it — so on a long letter, lines that were
       below the fold drift into view right as they're about to go ---- */
    function followScroll(container, duration) {
      const maxScroll = container.scrollHeight - container.clientHeight;
      if (maxScroll <= 1) return;
      const start = performance.now();
      function tick(now) {
        const t = Math.min(1, (now - start) / duration);
        const eased = t * t * (3 - 2 * t); // smoothstep, gentler than linear
        container.scrollTop = eased * maxScroll;
        if (t < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }

    function scrambleAndErase(spans, totalLines, scrollEl) {
      return new Promise((resolve) => {
        if (!spans.length) { resolve(); return; }
        const timers = [];

        // longer letters get a slower, more drawn-out animation
        const charCount = spans.filter((s) => s.dataset.orig.trim()).length;
        const lengthScale = Math.min(1 + Math.max(charCount - 20, 0) / 90, 2.4);

        const scrambleSpread = 550 * lengthScale;  // scramble wave sweep time, within a line
        const lineStagger = 80 * lengthScale;       // extra delay added per line
        const eraseOffset = 240 * lengthScale;      // gap before the erase wave starts, so it overlaps the scramble wave
        const eraseSpread = 550 * lengthScale;       // erase wave sweep time, within a line
        const fadeDuration = Math.min(480 * lengthScale, 900); // per-character fade-out length

        const maxColByLine = {};
        spans.forEach((s) => {
          const li = s.dataset.line;
          const c = Number(s.dataset.col) || 0;
          maxColByLine[li] = Math.max(maxColByLine[li] || 0, c);
        });

        const lineOrder = LINE_DIRECTION === 1
          ? (li) => li
          : (li) => (totalLines - 1 - li);

        spans.forEach((span) => {
          const line = Number(span.dataset.line);
          const col = Number(span.dataset.col) || 0;
          const maxCol = maxColByLine[span.dataset.line] || 1;
          const colFrac = col / maxCol; // 1 = rightmost, 0 = leftmost, within its own line
          const lineDelay = lineOrder(line) * lineStagger;

          const scrambleDelay = lineDelay + (1 - colFrac) * scrambleSpread + Math.random() * 60;
          const eraseDelay = lineDelay + eraseOffset + (1 - colFrac) * eraseSpread + Math.random() * 60;
          const stopDelay = eraseDelay + fadeDuration;

          if (span.dataset.orig.trim()) {
            let iv = null;
            timers.push(setTimeout(() => {
              span.classList.add('is-scrambling');
              iv = setInterval(() => {
                span.textContent = GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)];
              }, 45);
            }, scrambleDelay));
            timers.push(setTimeout(() => { if (iv) clearInterval(iv); }, stopDelay));
          }

          timers.push(setTimeout(() => {
            span.style.animationDuration = `${fadeDuration}ms`;
            span.classList.add('is-erasing');
          }, eraseDelay));
        });

        const totalDuration = (totalLines - 1) * lineStagger + eraseOffset + eraseSpread + fadeDuration + 120;
        if (scrollEl) followScroll(scrollEl, totalDuration);
        timers.push(setTimeout(resolve, totalDuration));
      });
    }

    sendBtn.addEventListener('click', async () => {
      const name = from.value.trim();
      const message = body.value.trim();
      if (!message) {
        setStatus('write something first?', 'var(--text-dim)');
        body.focus();
        return;
      }

      sendBtn.disabled = true;
      from.disabled = true;
      body.disabled = true;
      setMode('sending');
      dot.classList.remove('is-dirty', 'is-sent');
      dot.classList.add('is-sending');

      // "from" is the topmost line if present; the letter body follows it
      const fromResult = buildGlitchSpans(glitchFrom, from.value);
      const bodyResult = buildGlitchSpans(glitch, body.value);
      bodyResult.spans.forEach((s) => { s.dataset.line = Number(s.dataset.line) + fromResult.lineCount; });
      const totalLines = fromResult.lineCount + bodyResult.lineCount;
      const allSpans = [...fromResult.spans, ...bodyResult.spans];

      if (fromResult.spans.length) glitchFrom.classList.add('is-active');
      glitch.classList.add('is-active');
      from.classList.add('is-sending');
      body.classList.add('is-sending');

      setStatus('sending…', 'var(--warn)');
      const animationDone = scrambleAndErase(allSpans, totalLines, glitch);

      let res, data, networkError = null;
      try {
        [res] = await Promise.all([
          fetch('/letters/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, body: message, device: collectDeviceInfo() }),
          }),
          animationDone,
        ]);
        data = await res.json().catch(() => ({}));
      } catch (err) {
        networkError = err;
        await animationDone;
      }

      glitch.classList.remove('is-active');
      glitchFrom.classList.remove('is-active');
      glitch.scrollTop = 0;
      dot.classList.remove('is-sending');
      from.disabled = false;
      body.disabled = false;

      if (networkError || !res || !res.ok) {
        body.classList.remove('is-sending');
        from.classList.remove('is-sending');
        setMode('normal');
        dot.classList.add('is-dirty');
        setStatus(
          networkError
            ? 'network hiccup — try again.'
            : ((data && data.error) || 'that didn\u2019t go through — try again in a bit.'),
          'var(--text-dim)'
        );
        sendBtn.disabled = false;
        return;
      }

      // clear the real fields before they're revealed again, so they
      // come back empty instead of flashing the old text before it's wiped
      body.value = '';
      from.value = '';
      updateCount();
      updatePos();
      body.classList.remove('is-sending');
      from.classList.remove('is-sending');

      setMode('sent');
      dot.classList.add('is-sent');
      setStatus(
        name ? `thanks, ${name}!` : 'sent!',
        'var(--ok)'
      );

      if (typeof data.total === 'number' && currentTotal !== null) {
        animateCount(statNum, currentTotal, data.total, 700);
        currentTotal = data.total;
      } else if (typeof data.total === 'number') {
        currentTotal = data.total;
        statNum.textContent = currentTotal.toLocaleString();
      }

      setTimeout(() => {
        sendBtn.disabled = false;
        dot.classList.remove('is-sent');
        setMode('normal');
      }, 1800);
    });

    updateCount();
    updatePos();
    loadInitialCount();
  }

  /* ------------------------------------------------------------
     FAKE LINKS — this is a mock; keep them inert but honest
     ------------------------------------------------------------ */
  function wireFakeLinks(scope = document) {
    scope.querySelectorAll('[data-fake-link]').forEach((a) => {
      a.addEventListener('click', (e) => e.preventDefault());
    });
  }

  /* ------------------------------------------------------------
     COMMAND PALETTE
     ------------------------------------------------------------ */
  function initCommandPalette() {
    const overlay = document.getElementById('cmdkOverlay');
    const panel = document.getElementById('cmdk');
    const input = document.getElementById('cmdkInput');
    const output = document.getElementById('cmdkOutput');
    const trigger = document.getElementById('cmdkTrigger');

    let lastFocused = null;

    const open = () => {
      lastFocused = document.activeElement;
      overlay.hidden = false;
      panel.hidden = false;
      input.value = '';
      output.innerHTML = '';
      requestAnimationFrame(() => input.focus());
      document.addEventListener('keydown', onKeydown);
    };

    const close = () => {
      overlay.hidden = true;
      panel.hidden = true;
      document.removeEventListener('keydown', onKeydown);
      if (lastFocused) lastFocused.focus();
    };

    const print = (text, isCommand = false) => {
      const line = document.createElement('div');
      line.className = 'line' + (isCommand ? ' line--cmd' : '');
      line.textContent = text;
      output.appendChild(line);
      output.scrollTop = output.scrollHeight;
    };

    const jump = (view, label) => {
      print(`jumping to ${label}…`);
      setTimeout(() => { goToView(view); close(); }, 120);
    };

    const commands = {
      help() { print('available: help, about, projects, server, music, letter, links, fortune, clear, duck'); },
      about() { jump('about', 'about'); },
      projects() { jump('projects', 'projects'); },
      server() { jump('server', 'server'); },
      music() { jump('music', 'music'); },
      letter() { jump('letter', 'letter'); },
      links() { jump('links', 'links'); },
      home() { jump('home', 'home'); },
      fortune() {
        const fortunes = [
          'im not wise enough to write these. maybe you could send me some of your own wisdom?'
        ];
        print(fortunes[Math.floor(Math.random() * fortunes.length)]);
      },
      clear() { output.innerHTML = ''; },
      duck() {
        print('quack.');
        const duck = document.createElement('div');
        duck.className = 'duck';
        duck.textContent = '\uD83E\uDD86';
        duck.setAttribute('aria-hidden', 'true');
        document.body.appendChild(duck);
        setTimeout(() => duck.remove(), 2200);
      },
    };

    function run(raw) {
      const cmd = raw.trim().toLowerCase();
      if (!cmd) return;
      print(cmd, true);
      if (commands[cmd]) commands[cmd]();
      else print(`command not found: ${cmd}. type 'help' for a list.`);
    }

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { run(input.value); input.value = ''; }
    });

    function onKeydown(e) { if (e.key === 'Escape') close(); }

    if (trigger) trigger.addEventListener('click', open);
    if (overlay) overlay.addEventListener('click', close);

    document.addEventListener('keydown', (e) => {
      if (e.key !== '/') return;
      if (isTypingTarget(document.activeElement)) return;
      if (!overlay || !panel) return;
      e.preventDefault();
      open();
    });
  }

  /* ------------------------------------------------------------
     MUSIC PLAYER — floating bar, only visible while a track is
     loaded and playing/paused; custom play/seek/volume controls
     wired to .track buttons, plus timed "comments" that surface
     one at a time as playback reaches them.

     Add comments per-track by filename (matches the audio file
     in the src, e.g. .../music/isnt_she_lovely.mp3 -> key below):
       start:    seconds into the track
       duration: how long the comment stays on screen (seconds)
       text:     the comment itself
     ------------------------------------------------------------ */
  const TRACK_COMMENTS = {
    'isnt_she_lovely.m4a': [
      { start: 1, duration: 7, text: 'despite the controversy around this, i still really like this take of the song' },
      { start: 9, duration: 6, text: 'really tried to match the energy with this arrangement :p'},
      { start: 15.2, duration: 3.5, text: 'IISSNNTT SHEE PREECCIOOUUSSS' },
      { start: 19, duration: 3.5, text: 'LESS THAAN ONEE MIIINNUTTEE OLDD' },
      { start: 23, duration: 16, text: 'ᕕ( ᐛ )ᕗᕕ( ᐕ )ᕗ' }
    ],
    'stay_with_me.mp3': [
      { start: 0.4, duration: 5.6, text: 'another awesome arrangement by soul :)' },
      { start: 6.5, duration: 6, text: 'sorry if the audios muffled, the chorus is worth it, trust!' },
      { start: 13, duration: 4, text: '♪' },
      { start: 19.2, duration: 1.3, text: 'watashi wa watashi ♪' },
      { start: 20.9, duration: 2, text: 'anata wa anata to ♪' },
      { start: 26.5, duration: 1.55, text: 'yuube i-itetta ♪' }, 
      { start: 28.5, duration: 2.3, text: 'sonna ki mo suru wa ♪' },
      { start: 34, duration: 2.4, text: 'gurei no jaketto ni ♪' },
      { start: 36.7, duration: 1.8, text: 'mioboe ga aru ♪' },
      { start: 38.7, duration: 2, text: 'koohii no shimi ♪' },
      { start: 41.4, duration: 1.9, text: 'STAYY WITH MEEEEEE ♪' }, 
      { start: 43.8, duration: 3, text: 'MAYONAKA NO DOA O TATAKIIII ♪' },
      { start: 47.8, duration: 3, text: 'KAERANAI DE TOOO NAAIIITTAA ♪ ' },
      { start: 54, duration: 1, text: 'oops' },
      { start: 55.5, duration: 1.8, text: 'ano kisetsu ga ♪' },
      { start: 57.8, duration: 2, text: 'ima me no mae ♪' },
      { start: 60, duration: 2, text: 'stay with-' }
    ],
    'from_the_start': [

    ]
  };

  function initMusicPlayer() {
    const player = document.getElementById('musicPlayer');
    const audio = document.getElementById('audioPlayer');
    const title = document.getElementById('playerTitle');
    const titleBox = document.getElementById('playerTitleBox');
    const closeBtn = document.getElementById('musicPlayerClose');
    const toggleBtn = document.getElementById('playerToggle');
    const track = document.getElementById('playerTrack');
    const trackFill = document.getElementById('playerTrackFill');
    const trackThumb = document.getElementById('playerTrackThumb');
    const curTimeEl = document.getElementById('playerTime');
    const durTimeEl = document.getElementById('playerDuration');
    const volume = document.getElementById('playerVolume');
    const commentEl = document.getElementById('playerComment');
    const tracks = Array.from(document.querySelectorAll('.track'));
    if (!player || !audio) return;

    let comments = [];
    let activeComment = null;
    let dragging = false;

    function fmt(t) {
      if (!isFinite(t) || t < 0) return '0:00';
      const m = Math.floor(t / 60);
      const s = Math.floor(t % 60).toString().padStart(2, '0');
      return `${m}:${s}`;
    }

    function keyFor(src) {
      return src.split('/').pop();
    }

    function show() {
      player.classList.add('is-visible');
      player.setAttribute('aria-hidden', 'false');
    }
    function hide() {
      player.classList.remove('is-visible', 'is-paused');
      player.setAttribute('aria-hidden', 'true');
      hideComment();
    }

    function showComment(text) {
      commentEl.textContent = text;
      commentEl.classList.add('is-visible');
    }
    function hideComment() {
      commentEl.classList.remove('is-visible');
      activeComment = null;
    }

    function setPlayIcon(isPlaying) {
      toggleBtn.textContent = isPlaying ? '❚❚' : '▶';
      toggleBtn.setAttribute('aria-label', isPlaying ? 'pause' : 'play');
    }

    // title marquee — only scrolls (right-to-left, looping) when the
    // text is actually wider than its box; otherwise sits still
    function setTitle(text) {
      title.classList.remove('is-marquee');
      title.style.removeProperty('--marquee-duration');
      title.textContent = text;

      requestAnimationFrame(() => {
        const boxWidth = titleBox.clientWidth;
        const textWidth = title.scrollWidth;
        if (textWidth > boxWidth + 2) {
          const gap = '\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0•\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0';
          title.textContent = text + gap + text + gap;
          const singleWidth = title.scrollWidth / 2;
          const pxPerSecond = 40;
          const duration = Math.max(5, singleWidth / pxPerSecond);
          title.style.setProperty('--marquee-duration', duration + 's');
          title.classList.add('is-marquee');
        }
      });
    }

    // custom seek track — pointer events unify mouse + touch, so a
    // single tap jumps to that spot and a press-drag scrubs smoothly
    // without the click also registering as a seek
    function ratioFromEvent(e) {
      const rect = track.getBoundingClientRect();
      const x = e.clientX - rect.left;
      return Math.min(1, Math.max(0, rect.width ? x / rect.width : 0));
    }

    function paintProgress(ratio) {
      const pct = ratio * 100;
      trackFill.style.width = pct + '%';
      trackThumb.style.left = pct + '%';
      track.setAttribute('aria-valuenow', Math.round(pct));
    }

    track.addEventListener('pointerdown', (e) => {
      dragging = true;
      track.classList.add('is-dragging');
      track.setPointerCapture(e.pointerId);
      const ratio = ratioFromEvent(e);
      paintProgress(ratio);
      if (audio.duration) curTimeEl.textContent = fmt(ratio * audio.duration);
    });
    track.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const ratio = ratioFromEvent(e);
      paintProgress(ratio);
      if (audio.duration) curTimeEl.textContent = fmt(ratio * audio.duration);
    });
    function finishDrag(e) {
      if (!dragging) return;
      dragging = false;
      track.classList.remove('is-dragging');
      if (audio.duration) {
        const ratio = ratioFromEvent(e);
        audio.currentTime = ratio * audio.duration;
      }
    }
    track.addEventListener('pointerup', finishDrag);
    track.addEventListener('pointercancel', () => {
      dragging = false;
      track.classList.remove('is-dragging');
    });
    track.addEventListener('keydown', (e) => {
      if (!audio.duration) return;
      let delta = 0;
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp') delta = 5;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') delta = -5;
      if (!delta) return;
      e.preventDefault();
      audio.currentTime = Math.min(audio.duration, Math.max(0, audio.currentTime + delta));
    });

    tracks.forEach((btn) => {
      btn.addEventListener('click', () => {
        const src = btn.dataset.src;
        const name = btn.querySelector('.tracklist__name');
        if (src && !audio.src.endsWith(src)) {
          audio.src = src;
          comments = TRACK_COMMENTS[keyFor(src)] || [];
          hideComment();
        }
        setTitle(name ? name.textContent : 'now playing');
        tracks.forEach((t) => t.classList.remove('is-playing'));
        btn.classList.add('is-playing');
        audio.play().catch(() => {});
      });
    });

    audio.addEventListener('loadedmetadata', () => {
      durTimeEl.textContent = fmt(audio.duration);
    });

    audio.addEventListener('timeupdate', () => {
      if (!dragging) {
        paintProgress(audio.duration ? audio.currentTime / audio.duration : 0);
      }
      curTimeEl.textContent = fmt(audio.currentTime);

      const match = comments.find(
        (c) => audio.currentTime >= c.start && audio.currentTime < c.start + c.duration
      );
      if (match !== activeComment) {
        if (match) showComment(match.text);
        else hideComment();
        activeComment = match || null;
      }
    });

    volume.addEventListener('input', () => {
      audio.volume = Number(volume.value);
    });
    audio.volume = Number(volume.value);

    toggleBtn.addEventListener('click', () => {
      if (audio.paused) audio.play().catch(() => {});
      else audio.pause();
    });

    audio.addEventListener('play', () => {
      player.classList.remove('is-paused');
      setPlayIcon(true);
      show();
    });
    audio.addEventListener('pause', () => {
      if (!audio.ended) {
        player.classList.add('is-paused');
        setPlayIcon(false);
        show();
      }
    });
    audio.addEventListener('ended', () => {
      setPlayIcon(false);
      hide();
      tracks.forEach((t) => t.classList.remove('is-playing'));
    });

    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        audio.pause();
        audio.currentTime = 0;
        tracks.forEach((t) => t.classList.remove('is-playing'));
        hide();
      });
    }

    hide();
  }

  /* ------------------------------------------------------------
     PAGE TRANSITIONS — a short fade between home and /auth/login
     since those are real page loads, not tab switches
     ------------------------------------------------------------ */
  function initPageTransitions() {
    const EXIT_MS = 200;

    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href]');
      if (!link || link.target === '_blank') return;

      const href = link.getAttribute('href');
      const path = window.location.pathname;
      const goingToLogin = href === '/auth/login' && path !== '/auth/login';
      const goingHome = href === '/' && path.startsWith('/auth/login');
      if (!goingToLogin && !goingHome) return;

      e.preventDefault();
      document.body.classList.add('is-leaving');
      setTimeout(() => { window.location.href = href; }, EXIT_MS);
    });
  }

  /* ------------------------------------------------------------
     BOOT
     ------------------------------------------------------------ */
  document.addEventListener('DOMContentLoaded', () => {
    typeHero();
    initNav();
    initProjects();
    initClock();
    initLetter();
    wireFakeLinks();
    initPageTransitions();
    initCommandPalette();
    initMusicPlayer();
    restartStagger(document.getElementById('panel-home'));
  });
})();
