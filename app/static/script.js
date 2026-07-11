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

  async function fetchMetrics() {
    const fills = document.querySelectorAll('[data-metric]');
    const uptimeEl = document.getElementById('uptimeVal');

    try {
      const res = await fetch('/dashboard/api/public-stats');
      if (!res.ok) return;
      const data = await res.json();
      const state = { cpu: data.cpu, ram: data.ram, disk: data.disk };

      fills.forEach((fill) => {
        const key = fill.dataset.metric;
        if (!(key in state) || state[key] == null) return;
        const val = Math.round(state[key]);
        fill.style.width = val + '%';
        const valEl = document.querySelector(`[data-metric-val="${key}"]`);
        if (valEl) valEl.textContent = val + '%';
        const bar = fill.closest('.meters__bar');
        if (bar) bar.setAttribute('aria-label', `${key.toUpperCase()} usage ${val} percent`);
      });

      if (uptimeEl && data.uptime) uptimeEl.textContent = `uptime ${data.uptime}`;
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
  function initLetter() {
    const body = document.getElementById('letterBody');
    const from = document.getElementById('letterFrom');
    const gutter = document.getElementById('editorGutter');
    const mode = document.getElementById('editorMode');
    const count = document.getElementById('editorCount');
    const dot = document.getElementById('editorDot');
    const sendBtn = document.getElementById('sendLetter');
    const confirm = document.getElementById('editorConfirm');
    if (!body) return;

    function updateGutter() {
      const lines = Math.max(1, body.value.split('\n').length);
      gutter.textContent = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
    }

    function updateCount() {
      const words = body.value.trim() ? body.value.trim().split(/\s+/).length : 0;
      count.textContent = `${words} word${words === 1 ? '' : 's'}`;
    }

    function markDirty() {
      const hasContent = body.value.trim() || from.value.trim();
      dot.classList.toggle('is-dirty', Boolean(hasContent));
      dot.classList.remove('is-sent');
      sendBtn.disabled = false;
      confirm.textContent = '';
    }

    body.addEventListener('input', () => { updateGutter(); updateCount(); markDirty(); });
    from.addEventListener('input', markDirty);
    body.addEventListener('focus', () => (mode.textContent = '-- INSERT --'));
    body.addEventListener('blur', () => (mode.textContent = '-- NORMAL --'));

    sendBtn.addEventListener('click', async () => {
      const name = from.value.trim();
      const message = body.value.trim();
      if (!message) {
        confirm.textContent = 'write something first — even one line is fine.';
        confirm.style.color = 'var(--text-dim)';
        body.focus();
        return;
      }

      sendBtn.disabled = true;
      confirm.style.color = 'var(--text-dim)';
      confirm.textContent = 'sending…';

      try {
        const res = await fetch('/letters/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, body: message }),
        });
        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
          confirm.style.color = 'var(--text-dim)';
          confirm.textContent = data.error || 'that didn\u2019t go through — try again in a bit.';
          sendBtn.disabled = false;
          return;
        }

        dot.classList.remove('is-dirty');
        dot.classList.add('is-sent');
        confirm.style.color = 'var(--ok)';
        confirm.textContent = name
          ? `sent — thanks, ${name}. it's in the inbox now.`
          : 'sent — it\u2019s in the inbox now.';

        setTimeout(() => {
          body.value = '';
          from.value = '';
          updateGutter();
          updateCount();
          sendBtn.disabled = false;
          dot.classList.remove('is-sent');
        }, 2200);
      } catch (err) {
        confirm.style.color = 'var(--text-dim)';
        confirm.textContent = 'network hiccup — try again.';
        sendBtn.disabled = false;
      }
    });

    updateGutter();
    updateCount();
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
