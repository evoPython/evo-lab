/* ============================================================
   EVO.FTP.SH — home page (redesign)
   Nav + a horizontally-sliding track of panels, driven by the
   URL hash. Merged from two sources:
     - layout/interaction (routing, sticky notes, piano, project
       modal) comes from the new design
     - the letter box is the real, backend-wired feature from the
       previous design (POSTs to /letters/send, same element IDs),
       just restyled to fit here
   The old system-stats view and in-page music player were dropped
   in the redesign and are intentionally not present.
   ============================================================ */
(() => {
  'use strict';

  /* ------------------------------------------------------------
     CLOCK — topbar greet/clock. Present on every page that still
     uses base.html's default topbar (home overrides it away).
     ------------------------------------------------------------ */
  function initClock() {
    const clockEl = document.getElementById('clock');
    const greetEl = document.getElementById('greet');
    if (!clockEl && !greetEl) return;
    const greetings = [
      [5, 11, 'good morning!'],
      [11, 17, 'good afternoon.'],
      [17, 21, 'good evening.'],
      [21, 24, 'up late too?'],
      [0, 3, 'what are you doing up so late?'],
      [3, 5, 'you need to sleep.'],
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
     SERVER METRICS — used by the /dashboard sysgrid widget (and
     any other standalone page that embeds it). No longer part of
     the home page itself, but still a real, live-polled feature
     elsewhere on the site.
     ------------------------------------------------------------ */
  let metricsTimer = null;
  let cpuGraphBuilt = false;
  const CPU_HISTORY_LEN = 28;
  const cpuHistory = [];
  let currentBatteryHours = 1;
  const BATTERY_REFRESH_EVERY_N_TICKS = 20; // 20 * 3s = ~60s
  let batteryTickCounter = 0;
  const BATTERY_VIEW_W = 300;
  const BATTERY_VIEW_H = 46;

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

  function buildBatterySvg(history) {
    if (!history || history.length < 2) return '';

    const minTs = history[0].ts;
    const maxTs = history[history.length - 1].ts;
    const span = Math.max(maxTs - minTs, 1);
    const pad = 3;
    const usableH = BATTERY_VIEW_H - pad * 2;

    const points = history.map((p) => ({
      x: ((p.ts - minTs) / span) * BATTERY_VIEW_W,
      y: pad + usableH - (Math.max(0, Math.min(100, p.percent)) / 100) * usableH,
      charging: p.charging,
    }));

    const linePath = points
      .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
      .join(' ');
    const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${BATTERY_VIEW_H} `
      + `L${points[0].x.toFixed(1)},${BATTERY_VIEW_H} Z`;

    const chargeDots = points
      .filter((p) => p.charging)
      .map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${(BATTERY_VIEW_H - 1.5).toFixed(1)}" r="1.3" class="battery-chart__charge-dot" />`)
      .join('');

    const last = points[points.length - 1];

    return `<svg viewBox="0 0 ${BATTERY_VIEW_W} ${BATTERY_VIEW_H}" preserveAspectRatio="none" class="battery-chart">`
      + `<line x1="0" y1="${(pad + usableH / 2).toFixed(1)}" x2="${BATTERY_VIEW_W}" y2="${(pad + usableH / 2).toFixed(1)}" class="battery-chart__midline" />`
      + `<path d="${areaPath}" class="battery-chart__area" />`
      + `<path d="${linePath}" class="battery-chart__line" />`
      + chargeDots
      + `<circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="2" class="battery-chart__dot" />`
      + `</svg>`;
  }

  function formatBatteryTick(hours) {
    if (hours > 24) return (ts) => new Date(ts * 1000).toLocaleDateString([], { weekday: 'short' });
    if (hours > 1) return (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric' });
    return (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function renderBatteryGraph(history, hours) {
    const graph = document.getElementById('batteryGraph');
    const ticksEl = document.getElementById('batteryTicks');
    if (graph) graph.innerHTML = buildBatterySvg(history);

    if (!ticksEl) return;
    if (!history || history.length < 2) {
      ticksEl.innerHTML = '';
      return;
    }
    const fmt = formatBatteryTick(hours);
    const first = history[0].ts;
    const mid = history[Math.floor(history.length / 2)].ts;
    const last = history[history.length - 1].ts;
    ticksEl.innerHTML = [first, mid, last].map((ts) => `<span>${fmt(ts)}</span>`).join('');
  }

  async function fetchBatteryHistory() {
    try {
      const res = await fetch(`/dashboard/api/battery-history?hours=${currentBatteryHours}`);
      if (!res.ok) return;
      const history = await res.json();
      renderBatteryGraph(history, currentBatteryHours);
    } catch (err) {
      // server unreachable — leave the last known graph on screen
    }
  }

  function initBatteryRangeTabs() {
    const wrap = document.getElementById('batteryRangeTabs');
    if (!wrap) return;
    const opts = Array.from(wrap.querySelectorAll('.battery-range__opt'));
    opts.forEach((opt) => {
      opt.addEventListener('click', () => {
        const hours = parseFloat(opt.dataset.hours);
        if (!hours || hours === currentBatteryHours) return;
        currentBatteryHours = hours;
        opts.forEach((o) => {
          const active = o === opt;
          o.classList.toggle('is-active', active);
          o.setAttribute('aria-selected', String(active));
        });
        fetchBatteryHistory();
      });
    });
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

      ['ram', 'swap'].forEach((key) => {
        const val = Math.round(data[key]);
        const fill = document.querySelector(`[data-fill="${key}"]`);
        const valEl = document.querySelector(`[data-val="${key}"]`);
        if (fill) { fill.style.width = val + '%'; setLevel(fill, val); }
        if (valEl) { valEl.textContent = val + '%'; }
      });
      if (ramSubEl) ramSubEl.textContent = `${data.ram_used_gb} / ${data.ram_total_gb} gb`;

      const diskVal = Math.round(data.disk);
      const diskFill = document.querySelector('[data-fill="disk"]');
      const diskValEl = document.querySelector('[data-val="disk"]');
      if (diskFill) { diskFill.style.width = diskVal + '%'; setLevel(diskFill, diskVal); }
      if (diskValEl) { diskValEl.textContent = diskVal + '%'; setLevel(diskValEl, diskVal); }
      if (diskSubEl) diskSubEl.textContent = `${data.disk_used_gb} / ${data.disk_total_gb} gb`;

      if (netSentEl) netSentEl.textContent = formatRate(data.net_sent_bps);
      if (netRecvEl) netRecvEl.textContent = formatRate(data.net_recv_bps);

      const battValEl = document.querySelector('[data-val="battery"]');
      const battStatusEl = document.getElementById('batteryStatus');
      if (data.battery) {
        const battVal = Math.round(data.battery.percent);
        if (battValEl) {
          battValEl.textContent = battVal + '%';
          battValEl.classList.remove('is-warn', 'is-danger');
          if (!data.battery.charging) {
            if (battVal <= 15) battValEl.classList.add('is-danger');
            else if (battVal <= 30) battValEl.classList.add('is-warn');
          }
        }
        if (battStatusEl) battStatusEl.textContent = data.battery.charging ? 'charging' : 'on battery';
      } else {
        if (battValEl) battValEl.textContent = 'n/a';
        if (battStatusEl) battStatusEl.textContent = 'no battery';
      }

      batteryTickCounter++;
      if (batteryTickCounter % BATTERY_REFRESH_EVERY_N_TICKS === 0) fetchBatteryHistory();

      if (data.mode) setPowerModeUI(data.mode);

      if (uptimeEl && data.uptime) uptimeEl.textContent = `uptime ${data.uptime}`;
      if (procEl && data.processes) procEl.textContent = `${data.processes} proc`;
    } catch (err) {
      // server unreachable — just leave the last known values on screen
    }
  }

  function startMetrics() {
    if (metricsTimer) return;
    fetchMetrics();
    fetchBatteryHistory();
    metricsTimer = setInterval(fetchMetrics, 3000);
  }

  function stopMetrics() {
    clearInterval(metricsTimer);
    metricsTimer = null;
  }

  function setPowerModeUI(mode) {
    const group = document.getElementById('powerMode');
    if (!group) return;
    const opts = Array.from(group.querySelectorAll('.powermode__opt'));
    opts.forEach((opt) => {
      opt.classList.toggle('is-active', opt.dataset.mode === mode);
    });
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
     Shared boot — runs on every page that loads this file
     ------------------------------------------------------------ */
  document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initPageTransitions();
    initBatteryRangeTabs();

    // Standalone pages that embed the sysgrid widget (e.g. /dashboard)
    // have no home-page router to start/stop metrics polling for
    // them, so kick polling off directly whenever that widget is on
    // the page at all.
    if (document.getElementById('sysgrid')) startMetrics();
  });

  /* ------------------------------------------------------------
     Everything below is specific to the home page's own layout
     and only runs when #homeApp is present.
     ------------------------------------------------------------ */
  const homeApp = document.getElementById('homeApp');
  if (!homeApp) return; // this script also loads on non-home pages

  /* ------------------------------------------------------------
     INTRO — "welcome" gate, remembered for ~1.5h, then a smooth
     staggered reveal of the nav/track/footer either way.
     ------------------------------------------------------------ */
  (function initIntro() {
    const overlay = document.getElementById('introOverlay');
    const btn = document.getElementById('introBtn');
    const TTL = 90 * 60 * 1000; // ~1.5 hours, then it shows again
    const savedTs = parseInt(localStorage.getItem('rh_intro_ts') || '0', 10);
    const stillFresh = savedTs && (Date.now() - savedTs < TTL);

    function reveal() {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        homeApp.classList.add('rh-revealed');
        // lets pfp-float.js (a separate script, no shared scope) know
        // the nav/track/footer reveal has kicked off, so it can time
        // the pfp's own entrance to land just after theirs settles.
        document.dispatchEvent(new CustomEvent('rh:revealed'));
      }));
    }

    if (!overlay || stillFresh) {
      overlay?.remove();
      reveal();
      return;
    }

    btn?.addEventListener('click', () => {
      localStorage.setItem('rh_intro_ts', String(Date.now()));
      overlay.classList.add('rh-intro--leaving');
      reveal();
      setTimeout(() => overlay.remove(), 650);
    });
  })();

  /* ------------------------------------------------------------
     ROUTER — hash-driven horizontal track, ← → to navigate
     ------------------------------------------------------------ */
  const ROUTES = ['home', 'about', 'projects', 'fun'];
  const track = document.getElementById('track');
  const navLinks = document.getElementById('navLinks');
  const navCursor = document.getElementById('navCursor');
  const footerPath = document.getElementById('footerPath');
  const backHint = document.getElementById('backHint');
  let currentIndex = 0;
  let currentFunSub = 'menu';

  function routeFromHash() {
    const h = (location.hash || '#home').slice(1);
    const base = h.split('/')[0];
    return ROUTES.includes(base) ? base : 'home';
  }

  /* ------------------------------------------------------------
     TAGLINE TYPEWRITER — types "student · programmer · musician"
     into place each time the home panel is (re)entered.
     ------------------------------------------------------------ */
  const taglineType = document.getElementById('taglineType');
  const TAGLINE_TEXT = 'student · programmer · musician';
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let taglineTimer = null;

  function typeTagline() {
    if (!taglineType) return;
    clearTimeout(taglineTimer);

    if (prefersReducedMotion) {
      taglineType.textContent = TAGLINE_TEXT;
      return;
    }

    taglineType.textContent = '';
    let i = 0;
    (function step() {
      const justTyped = TAGLINE_TEXT[i - 1];
      taglineType.textContent = TAGLINE_TEXT.slice(0, i);
      i++;
      if (i <= TAGLINE_TEXT.length) {
        // slower base pace with real per-character randomness, plus an
        // extra pause right after finishing a word (i.e. at a space)
        const base = 55 + Math.random() * 95;
        const wordPause = justTyped === ' ' ? 180 + Math.random() * 220 : 0;
        taglineTimer = setTimeout(step, base + wordPause);
      }
    })();
  }

  /* ------------------------------------------------------------
     CURSOR BLOB — press and hold anywhere spawns a glow blob at the
     pointer that eases toward it while held (lerped each frame, so
     it trails smoothly instead of snapping to raw pointer positions),
     then ripples outward and fades on release.
     ------------------------------------------------------------ */
  (function initCursorBlob() {
    const glowLayer = document.querySelector('#homeApp .rh-grid-glow');
    if (!glowLayer || prefersReducedMotion) return;

    const LERP = 0.08; // lower = smoother/laggier trail
    const active = new Map(); // pointerId -> { el, tx, ty, cx, cy }
    let rafId = null;

    // base <audio> is never itself played — each click clones it, so
    // rapid/overlapping clicks each get their own playback instead of
    // one clock cutting off the last.
    const clickSound = new Audio('/static/sfx/click.mp3');
    clickSound.volume = 0.5;
    const CLICK_PITCH_MIN = 0.85;
    const CLICK_PITCH_MAX = 1.15;
    function playClick() {
      const a = clickSound.cloneNode(true);
      a.volume = clickSound.volume;
      // playbackRate doubles as pitch here (no separate audio graph
      // needed) — a small random range per click so repeated clicks
      // don't all sound identical.
      a.playbackRate = CLICK_PITCH_MIN + Math.random() * (CLICK_PITCH_MAX - CLICK_PITCH_MIN);
      a.play().catch(() => {}); // ignore autoplay-policy rejections
    }

    function frame() {
      active.forEach((s) => {
        s.cx += (s.tx - s.cx) * LERP;
        s.cy += (s.ty - s.cy) * LERP;
        s.el.style.left = `${s.cx}px`;
        s.el.style.top = `${s.cy}px`;
      });
      rafId = requestAnimationFrame(frame);
    }

    document.addEventListener('pointerdown', (e) => {
      const blob = document.createElement('span');
      blob.className = 'rh-blob rh-blob--cursor';
      blob.style.left = `${e.clientX}px`;
      blob.style.top = `${e.clientY}px`;
      glowLayer.appendChild(blob);
      // playing a piano key fires its own note sound on down/up — skip
      // the click sfx for that interaction so the two don't stack.
      const isPiano = !!e.target.closest('.rh-piano');
      active.set(e.pointerId, { el: blob, tx: e.clientX, ty: e.clientY, cx: e.clientX, cy: e.clientY, isPiano });
      if (rafId === null) rafId = requestAnimationFrame(frame);
    });

    document.addEventListener('pointermove', (e) => {
      const s = active.get(e.pointerId);
      if (!s) return;
      s.tx = e.clientX;
      s.ty = e.clientY;
    });

    function release(e) {
      const s = active.get(e.pointerId);
      if (!s) return;
      active.delete(e.pointerId);
      if (active.size === 0 && rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      s.el.classList.add('is-releasing');
      s.el.addEventListener('animationend', () => s.el.remove(), { once: true });
      // safety net in case the animation event never fires
      setTimeout(() => s.el.remove(), 1400);
      if (!s.isPiano) playClick();
    }
    document.addEventListener('pointerup', release);
    document.addEventListener('pointercancel', release);
  })();

  function moveCursor(link) {
    if (!link || !navCursor || !navLinks) return;
    const linkRect = link.getBoundingClientRect();
    const parentRect = navLinks.getBoundingClientRect();
    navCursor.style.transform = `translateX(${linkRect.left - parentRect.left - 14}px)`;
  }

  function render() {
    const route = routeFromHash();
    const index = ROUTES.indexOf(route);
    currentIndex = index;

    if (track) track.style.transform = `translateX(-${index * 25}%)`;

    let activeLink = null;
    navLinks?.querySelectorAll('a').forEach((a) => {
      if (a.dataset.route === route) {
        a.setAttribute('aria-current', 'page');
        activeLink = a;
      } else {
        a.removeAttribute('aria-current');
      }
    });
    moveCursor(activeLink);
    if (footerPath) footerPath.textContent = `evo.ftp.sh/${route}`;

    if (route === 'home') {
      homeApp.querySelectorAll('#panel-home .fade-up').forEach((el) => {
        el.style.animation = 'none';
        void el.offsetWidth;
        el.style.animation = '';
      });
      typeTagline();
    }

    const parts = (location.hash || '').slice(1).split('/');
    if (parts[0] === 'projects' && parts[1]) {
      openProject(parts[1]);
    } else {
      closeModal(false);
    }

    if (parts[0] === 'fun') {
      const sub = ['piano', 'letter'].includes(parts[1]) ? parts[1] : 'menu';
      currentFunSub = sub;
      homeApp.querySelectorAll('.rh-fun-page').forEach((el) => {
        el.classList.toggle('active', el.dataset.funPage === sub);
      });
    } else {
      currentFunSub = 'menu';
    }
    backHint?.classList.toggle('is-visible', route === 'fun' && currentFunSub !== 'menu');
  }

  window.addEventListener('hashchange', render);
  window.addEventListener('resize', () => {
    const active = navLinks?.querySelector('a[aria-current="page"]');
    moveCursor(active);
  });

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (document.getElementById('modalOverlay')?.classList.contains('open')) return;

    if (e.key === 'Backspace' && routeFromHash() === 'fun' && currentFunSub !== 'menu') {
      e.preventDefault();
      location.hash = '#fun';
    } else if (e.key === 'ArrowRight') {
      const next = Math.min(currentIndex + 1, ROUTES.length - 1);
      location.hash = `#${ROUTES[next]}`;
    } else if (e.key === 'ArrowLeft') {
      const prev = Math.max(currentIndex - 1, 0);
      location.hash = `#${ROUTES[prev]}`;
    } else if (['1', '2', '3', '4'].includes(e.key)) {
      location.hash = `#${ROUTES[Number(e.key) - 1]}`;
    }
  });

  /* ------------------------------------------------------------
     SWIPE — left/right touch gestures move between panels
     ------------------------------------------------------------ */
  (function initSwipe() {
    const wrapper = document.querySelector('.rh-track-wrapper');
    if (!wrapper) return;

    if (localStorage.getItem('rh_swiped') === '1') homeApp.classList.add('rh-has-swiped');

    let startX = 0, startY = 0, tracking = false;

    wrapper.addEventListener('touchstart', (e) => {
      if (e.target.closest('.rh-note, .rh-piano, input, textarea')) { tracking = false; return; }
      if (document.getElementById('modalOverlay')?.classList.contains('open')) { tracking = false; return; }
      const t = e.touches[0];
      startX = t.clientX; startY = t.clientY; tracking = true;
    }, { passive: true });

    wrapper.addEventListener('touchend', (e) => {
      if (!tracking) return;
      tracking = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;
      if (Math.abs(dx) < 45 || Math.abs(dx) < Math.abs(dy) * 1.2) return;

      if (localStorage.getItem('rh_swiped') !== '1') {
        localStorage.setItem('rh_swiped', '1');
        homeApp.classList.add('rh-has-swiped');
      }

      if (dx < 0) {
        const next = Math.min(currentIndex + 1, ROUTES.length - 1);
        location.hash = `#${ROUTES[next]}`;
      } else {
        const prev = Math.max(currentIndex - 1, 0);
        location.hash = `#${ROUTES[prev]}`;
      }
    }, { passive: true });
  })();

  /* ------------------------------------------------------------
     PROJECTS — real project list + a bottom-sheet modal
     ------------------------------------------------------------ */
  const PROJECTS = [
    {
      id: 'evo-lab',
      title: 'evo-lab',
      glyph: '◆',
      tag: 'web',
      desc: 'A personal homelab run 24/7 on a 6 year old laptop.',
      tags: ['web'],
      link: '#',
      body: 'Started as a way to stop paying for hosting I didn\'t need, and turned into the thing this whole site runs on. It serves this page, a handful of internal tools, and whatever I\'m tinkering with that week — reverse proxied behind a single entry point, with cron jobs doing the parts I\'m too lazy to automate properly.',
    },
    {
      id: 'carwash-pos',
      title: 'carwash-pos',
      glyph: '◆',
      tag: 'web',
      desc: 'A Point of Sale system for a carwash based in Cebu City.',
      tags: ['web'],
      link: '#',
      body: 'Built for a real carwash that was still tracking transactions on paper. Handles queueing, service pricing, and daily totals, with a simple enough interface that staff picked it up in an afternoon. Runs on a low-spec machine on-site, syncing back for reporting.',
    },
    {
      id: 'riffmd',
      title: 'riffmd',
      glyph: '◆',
      tag: 'cli',
      desc: 'Rich Interface For Fetching Music Downloads. A terminal music downloader and player powered by Rich and yt-dlp.',
      tags: ['cli'],
      link: '#',
      body: 'A terminal-first way to grab and play music without leaving the shell. Wraps yt-dlp for fetching and uses Rich for a surprisingly pleasant text UI — queueing, searching, and basic playback, all without a browser tab in sight.',
    },
    {
      id: 'vault',
      title: 'vault',
      glyph: '◆',
      tag: 'writing',
      desc: 'Personal collection of notes organized with Zettelkasten in mind.',
      tags: ['writing'],
      link: '#',
      body: 'A plain-text note vault linked together Zettelkasten-style — small atomic notes, cross-referenced instead of folder-sorted. Mostly reading notes, half-formed ideas, and things I wanted to remember I once thought about.',
    },
  ];

  const projectList = document.getElementById('projectList');
  if (projectList) {
    PROJECTS.forEach((p) => {
      const row = document.createElement('a');
      row.href = `#projects/${p.id}`;
      row.className = 'rh-project-row';
      row.innerHTML = `
        <div class="rh-project-row__top">
          <span class="rh-project-row__title"><span class="glyph">${p.glyph}</span>${p.title}</span>
          <span class="rh-project-row__tag">${p.tag}</span>
        </div>
        <span class="rh-project-row__desc">${p.desc}</span>
        <span class="rh-project-row__tags">${p.tags.map((t) => `<span class="rh-tag">${t}</span>`).join('')}</span>
      `;
      projectList.appendChild(row);
    });
  }

  const modalOverlay = document.getElementById('modalOverlay');
  const modalContent = document.getElementById('modalContent');
  let lastFocused = null;

  function openProject(id) {
    const p = PROJECTS.find((x) => x.id === id);
    if (!p || !modalOverlay || !modalContent) return;
    lastFocused = document.activeElement;
    modalContent.innerHTML = `
      <button class="rh-modal__close" id="modalCloseBtn">close ✕</button>
      <h3 id="modalTitle"><span class="glyph">${p.glyph}</span> ${p.title}</h3>
      <p class="rh-modal__sub">${p.tag}</p>
      <div class="rh-field"><label>about</label><p>${p.desc}</p></div>
      <div class="rh-modal__gallery">
        <div class="rh-modal__visual" aria-hidden="true"><span class="rh-modal__visual-label">NO IMAGE</span></div>
        <div class="rh-modal__visual" aria-hidden="true"><span class="rh-modal__visual-label">NO IMAGE</span></div>
      </div>
      <div class="rh-field"><label>more</label><p>${p.body || ''}</p></div>
      <div class="rh-links"><a href="${p.link}" data-fake-link>source</a></div>
    `;
    modalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    wireFakeLinks(modalContent);
    document.getElementById('modalCloseBtn')?.addEventListener('click', () => {
      history.replaceState(null, '', '#projects');
      closeModal(true);
    });
    document.getElementById('modalCloseBtn')?.focus();
  }

  function closeModal(restoreFocus) {
    modalOverlay?.classList.remove('open');
    document.body.style.overflow = '';
    if (restoreFocus && lastFocused) lastFocused.focus();
  }

  modalOverlay?.addEventListener('click', (e) => {
    if (e.target === modalOverlay) {
      history.replaceState(null, '', '#projects');
      closeModal(true);
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOverlay?.classList.contains('open')) {
      history.replaceState(null, '', '#projects');
      closeModal(true);
    }
  });

  /* ------------------------------------------------------------
     FAKE LINKS — this is a mock; keep them inert but honest
     ------------------------------------------------------------ */
  function wireFakeLinks(scope = document) {
    scope.querySelectorAll('[data-fake-link]').forEach((a) => {
      a.addEventListener('click', (e) => e.preventDefault());
    });
  }

  /* ------------------------------------------------------------
     ABOUT — boring-version toggle + draggable sticky notes
     ------------------------------------------------------------ */
  const boringToggle = document.getElementById('boringToggle');
  const boringBox = document.getElementById('boringBox');
  boringToggle?.addEventListener('click', () => {
    const open = boringBox.classList.toggle('open');
    boringToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    boringToggle.textContent = open ? 'hide the boring version ↑' : 'prefer the boring version? →';
  });

  (function initBoard() {
    const board = document.getElementById('board');
    if (!board) return;
    let zTop = 10;

    board.querySelectorAll('.rh-note').forEach((note) => {
      let dragging = false;
      let startX, startY, origLeft, origTop, boardRect;

      function down(e) {
        note.setPointerCapture(e.pointerId);
        dragging = true;
        boardRect = board.getBoundingClientRect();
        const noteRect = note.getBoundingClientRect();
        startX = e.clientX; startY = e.clientY;
        origLeft = noteRect.left - boardRect.left;
        origTop = noteRect.top - boardRect.top;
        note.style.left = `${origLeft}px`;
        note.style.top = `${origTop}px`;
        note.classList.add('dragging');
        zTop += 1;
        note.style.zIndex = zTop;
      }
      function move(e) {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        const maxLeft = boardRect.width - note.offsetWidth;
        const maxTop = boardRect.height - note.offsetHeight;
        const clampedDx = Math.max(-origLeft, Math.min(dx, maxLeft - origLeft));
        const clampedDy = Math.max(-origTop, Math.min(dy, maxTop - origTop));
        // compositor-only transform during the drag itself — no layout thrash
        note.style.transform = `translate3d(${clampedDx}px, ${clampedDy}px, 0) rotate(var(--rot))`;
      }
      function up() {
        if (!dragging) return;
        dragging = false;
        // commit the drag offset into left/top once, then clear the transform
        const m = new DOMMatrixReadOnly(getComputedStyle(note).transform);
        note.style.left = `${origLeft + m.m41}px`;
        note.style.top = `${origTop + m.m42}px`;
        note.style.transform = '';
        note.classList.remove('dragging');
        note.classList.add('dropped');
        setTimeout(() => note.classList.remove('dropped'), 320);
      }

      note.addEventListener('pointerdown', down);
      note.addEventListener('pointermove', move);
      note.addEventListener('pointerup', up);
      note.addEventListener('pointercancel', up);

      note.addEventListener('keydown', (e) => {
        const step = 14;
        const rect = note.getBoundingClientRect();
        const bRect = board.getBoundingClientRect();
        let left = rect.left - bRect.left;
        let top = rect.top - bRect.top;
        let moved = true;
        if (e.key === 'ArrowRight') left += step;
        else if (e.key === 'ArrowLeft') left -= step;
        else if (e.key === 'ArrowDown') top += step;
        else if (e.key === 'ArrowUp') top -= step;
        else moved = false;
        if (moved) {
          e.preventDefault();
          const maxLeft = bRect.width - note.offsetWidth;
          const maxTop = bRect.height - note.offsetHeight;
          note.style.left = `${Math.max(0, Math.min(left, maxLeft))}px`;
          note.style.top = `${Math.max(0, Math.min(top, maxTop))}px`;
          zTop += 1;
          note.style.zIndex = zTop;
        }
      });
    });
  })();

  /* ------------------------------------------------------------
     FUN — playable mini piano
     ------------------------------------------------------------ */
  (function initPiano() {
    const NOTES = [
      { key: 'a', note: 'C4', freq: 261.63, black: false },
      { key: 'w', note: 'C#4', freq: 277.18, black: true, pos: 1 },
      { key: 's', note: 'D4', freq: 293.66, black: false },
      { key: 'e', note: 'D#4', freq: 311.13, black: true, pos: 2 },
      { key: 'd', note: 'E4', freq: 329.63, black: false },
      { key: 'f', note: 'F4', freq: 349.23, black: false },
      { key: 't', note: 'F#4', freq: 369.99, black: true, pos: 4 },
      { key: 'g', note: 'G4', freq: 392.00, black: false },
      { key: 'y', note: 'G#4', freq: 415.30, black: true, pos: 5 },
      { key: 'h', note: 'A4', freq: 440.00, black: false },
      { key: 'u', note: 'A#4', freq: 466.16, black: true, pos: 6 },
      { key: 'j', note: 'B4', freq: 493.88, black: false },
      { key: 'k', note: 'C5', freq: 523.25, black: false },
    ];

    const piano = document.getElementById('piano');
    if (!piano) return;
    let audioCtx = null;
    const activeVoices = {};

    function getCtx() {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      return audioCtx;
    }

    function noteOn(key) {
      if (activeVoices[key]) return;
      const n = NOTES.find((x) => x.key === key);
      if (!n) return;
      const ctx = getCtx();
      const now = ctx.currentTime;

      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(0.22, now + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 2.2);
      gain.connect(ctx.destination);

      const osc1 = ctx.createOscillator();
      osc1.type = 'triangle';
      osc1.frequency.value = n.freq;
      osc1.connect(gain);

      const osc2 = ctx.createOscillator();
      osc2.type = 'sine';
      osc2.frequency.value = n.freq * 2;
      const g2 = ctx.createGain();
      g2.gain.value = 0.06;
      osc2.connect(g2);
      g2.connect(gain);

      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 2.3);
      osc2.stop(now + 2.3);

      activeVoices[key] = { gain, osc1, osc2 };
      piano.querySelector(`[data-key="${key}"]`)?.classList.add('active');
    }

    function noteOff(key) {
      const v = activeVoices[key];
      if (v) {
        const ctx = getCtx();
        const now = ctx.currentTime;
        v.gain.gain.cancelScheduledValues(now);
        v.gain.gain.setTargetAtTime(0.0001, now, 0.04);
        delete activeVoices[key];
      }
      piano.querySelector(`[data-key="${key}"]`)?.classList.remove('active');
    }

    NOTES.forEach((n) => {
      const el = document.createElement('div');
      el.className = `rh-key${n.black ? ' black' : ''}`;
      el.dataset.key = n.key;
      el.textContent = n.key.toUpperCase();
      el.setAttribute('role', 'button');
      el.setAttribute('tabindex', '0');
      el.setAttribute('aria-label', `play ${n.note}`);
      if (n.black) el.style.left = `${n.pos * 12.5 - 3.5}%`;
      piano.appendChild(el);

      el.addEventListener('pointerdown', (e) => { e.preventDefault(); noteOn(n.key); });
      el.addEventListener('pointerup', () => noteOff(n.key));
      el.addEventListener('pointerleave', () => noteOff(n.key));
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); noteOn(n.key); }
      });
      el.addEventListener('keyup', (e) => {
        if (e.key === 'Enter' || e.key === ' ') noteOff(n.key);
      });
    });

    window.addEventListener('keydown', (e) => {
      if (e.repeat) return;
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (routeFromHash() !== 'fun') return;
      const k = e.key.toLowerCase();
      if (NOTES.some((n) => n.key === k)) noteOn(k);
    });
    window.addEventListener('keyup', (e) => {
      const k = e.key.toLowerCase();
      if (NOTES.some((n) => n.key === k)) noteOff(k);
    });
  })();

  /* ------------------------------------------------------------
     LETTER — a tiny editor, not a corporate form. This is the real
     feature (rate-limited, DB-backed via /letters/send + /letters/count),
     ported over from the previous design.
     ------------------------------------------------------------ */
  const GLITCH_CHARS = '!@#$%^&*<>[]{}/\\|_-=+~?01'.split('');

  function initLetter() {
    const body = document.getElementById('letterBody');
    const from = document.getElementById('letterFrom');
    const glitch = document.getElementById('editorGlitch');
    const glitchFrom = document.getElementById('editorGlitchFrom');
    const mode = document.getElementById('editorMode');
    const pos = document.getElementById('editorPos');
    const count = document.getElementById('editorCount');
    const dot = document.getElementById('editorDot');
    const sendBtn = document.getElementById('sendLetter');
    const confirmText = document.getElementById('editorConfirmText');
    const statNum = document.getElementById('letterStatNum');
    if (!body) return;

    let currentTotal = null;

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
      mode.dataset.mode = state;
      mode.textContent = state.toUpperCase();
    }

    let statusTimer = null;
    function setStatus(text, colorVar) {
      clearTimeout(statusTimer);
      const swap = () => {
        confirmText.textContent = text || '';
        confirmText.style.color = colorVar || '';
        if (!text) { confirmText.classList.remove('is-entering', 'is-leaving'); return; }
        confirmText.classList.add('is-entering');
        confirmText.classList.remove('is-leaving');
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

    const LINE_DIRECTION = 1;

    function buildGlitchSpans(container, text) {
      container.innerHTML = '';
      if (!text) return { spans: [], lineCount: 0 };
      const lines = text.split('\n');
      const spans = [];
      lines.forEach((line, li) => {
        let col = 0;
        for (const ch of line) {
          const span = document.createElement('span');
          span.className = 'rh-editor__glitch-char';
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

    function followScroll(container, duration) {
      const maxScroll = container.scrollHeight - container.clientHeight;
      if (maxScroll <= 1) return;
      const start = performance.now();
      function tick(now) {
        const t = Math.min(1, (now - start) / duration);
        const eased = t * t * (3 - 2 * t);
        container.scrollTop = eased * maxScroll;
        if (t < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }

    function scrambleAndErase(spans, totalLines, scrollEl) {
      return new Promise((resolve) => {
        if (!spans.length) { resolve(); return; }
        const timers = [];

        const charCount = spans.filter((s) => s.dataset.orig.trim()).length;
        const lengthScale = Math.min(1 + Math.max(charCount - 20, 0) / 90, 2.4);

        const scrambleSpread = 550 * lengthScale;
        const lineStagger = 80 * lengthScale;
        const eraseOffset = 240 * lengthScale;
        const eraseSpread = 550 * lengthScale;
        const fadeDuration = Math.min(480 * lengthScale, 900);

        const maxColByLine = {};
        spans.forEach((s) => {
          const li = s.dataset.line;
          const c = Number(s.dataset.col) || 0;
          maxColByLine[li] = Math.max(maxColByLine[li] || 0, c);
        });

        const lineOrder = LINE_DIRECTION === 1 ? (li) => li : (li) => (totalLines - 1 - li);

        spans.forEach((span) => {
          const line = Number(span.dataset.line);
          const col = Number(span.dataset.col) || 0;
          const maxCol = maxColByLine[span.dataset.line] || 1;
          const colFrac = col / maxCol;
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
        setStatus('write something first?', 'var(--rh-overlay0)');
        body.focus();
        return;
      }

      sendBtn.disabled = true;
      from.disabled = true;
      body.disabled = true;
      setMode('sending');
      dot.classList.remove('is-dirty', 'is-sent');
      dot.classList.add('is-sending');

      const fromResult = buildGlitchSpans(glitchFrom, from.value);
      const bodyResult = buildGlitchSpans(glitch, body.value);
      bodyResult.spans.forEach((s) => { s.dataset.line = Number(s.dataset.line) + fromResult.lineCount; });
      const totalLines = fromResult.lineCount + bodyResult.lineCount;
      const allSpans = [...fromResult.spans, ...bodyResult.spans];

      if (fromResult.spans.length) glitchFrom.classList.add('is-active');
      glitch.classList.add('is-active');
      from.classList.add('is-sending');
      body.classList.add('is-sending');

      setStatus('sending…', 'var(--rh-yellow)');
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
          networkError ? 'network hiccup — try again.' : ((data && data.error) || 'that didn\u2019t go through — try again in a bit.'),
          'var(--rh-overlay0)'
        );
        sendBtn.disabled = false;
        return;
      }

      body.value = '';
      from.value = '';
      updateCount();
      updatePos();
      body.classList.remove('is-sending');
      from.classList.remove('is-sending');

      setMode('sent');
      dot.classList.add('is-sent');
      setStatus(name ? `thanks, ${name}!` : 'sent!', 'var(--rh-green)');

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
     BOOT
     ------------------------------------------------------------ */
  initLetter();
  render();
})();
