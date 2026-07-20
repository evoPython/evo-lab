/* ============================================================
   GLOBAL MEDIA PLAYER
   Shared by music.html, dashboard.html, tools.html (any page that
   includes the _player_bar.html partial). Drives the bottom bar:
   laptop (mpv) playback, phone (<audio>) playback, or both — plus
   next/prev, which walks the downloaded-library list when the
   active source is our own player, or defers to playerctl (via
   /controls/media/next|prev) when it's "typical laptop media"
   (Spotify, a browser tab, etc).
   Polls continuously (independent of user action) so every open
   tab/device stays in sync with whatever's actually playing.
   ============================================================ */
(() => {
  'use strict';

  const bar = document.getElementById('music-player');
  if (!bar) return; // page doesn't include the player bar — nothing to do

  window.library = window.library || [];
  let current = null;          // { filename, title, uploader }
  let queue = null;            // playlist playback: { tracks, mode: 'loop'|'shuffle', index }
  let outputMode = 'laptop';   // 'laptop' | 'phone' | 'both'
  let statusTimer = null;
  let idleWatcher = null;
  let seeking = false;
  let readOnlyMode = false;

  const audio = document.getElementById('phone-audio'); // absent on the mini bar (dashboard) — laptop-only there
  const seekbar = document.getElementById('np-seekbar');

  function fmtTime(sec) {
    if (sec == null || isNaN(sec)) return '0:00';
    sec = Math.max(0, Math.floor(sec));
    const m = Math.floor(sec / 60);
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  // --- Library (shared across pages so next/prev can walk it even
  //     on dashboard/tools, which don't render the library list UI) ---

  async function loadLibrary() {
    try {
      const res = await fetch('/media/music/api/library');
      const data = await res.json();
      window.library = data.tracks || [];
    } catch (err) { /* ignore, next/prev just won't have data yet */ }
    if (typeof window.onLibraryLoaded === 'function') window.onLibraryLoaded();
  }
  window.loadLibrary = loadLibrary;

  // --- Playback ---

  function playTrack(filename, title, uploader, opts) {
    if (!(opts && opts.keepQueue)) queue = null;
    current = { filename, title, uploader };
    setReadOnlyMode(false);
    const dl = document.getElementById('np-download');
    if (dl) dl.style.display = 'none';
    document.getElementById('np-title').textContent = title || filename;
    document.getElementById('np-artist').textContent = uploader || '';

    if (outputMode === 'laptop' || outputMode === 'both') {
      postJSON('/media/music/api/play', { filename, title });
      startStatusPolling();
    }
    if (audio && (outputMode === 'phone' || outputMode === 'both')) {
      audio.src = '/media/music/stream/' + encodeURIComponent(filename);
      audio.currentTime = 0;
      audio.play().catch(() => {});
    }
    document.getElementById('np-toggle').innerHTML = '&#10074;&#10074;';
  }
  window.playTrack = playTrack;

  function togglePlay() {
    if (readOnlyMode) { postJSON('/controls/media/playpause', {}).then(() => setTimeout(checkIdleNowPlaying, 300)); return; }
    if (!current) return;
    if (outputMode === 'laptop' || outputMode === 'both') postJSON('/media/music/api/toggle', {});
    if (audio && (outputMode === 'phone' || outputMode === 'both')) {
      if (audio.paused) audio.play().catch(() => {}); else audio.pause();
    }
  }

  function stopPlayback() {
    if (readOnlyMode) return; // nothing of ours to stop — it's laptop-general media
    if (outputMode === 'laptop' || outputMode === 'both') postJSON('/media/music/api/stop', {});
    if (audio && (outputMode === 'phone' || outputMode === 'both')) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    current = null;
    queue = null;
    stopStatusPolling();
    resetNowPlayingUI();
  }

  function resetNowPlayingUI() {
    document.getElementById('np-title').textContent = 'Nothing playing';
    document.getElementById('np-artist').textContent = '';
    document.getElementById('np-toggle').innerHTML = '&#9654;';
    seekbar.value = 0;
    document.getElementById('np-position').textContent = '0:00';
    document.getElementById('np-duration').textContent = '0:00';
  }

  // --- Next / Previous ---
  // music-tool source: step through the downloaded library, looping.
  // laptop-media source (Spotify/browser/etc via playerctl): defer to it.

  function shuffleArray(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
  }

  // Starts playlist playback. `mode` is 'loop' (sequential, wraps) or
  // 'shuffle' (randomized order, reshuffled each time it wraps).
  function playQueue(tracks, mode) {
    if (!tracks.length) return;
    const list = tracks.slice();
    if (mode === 'shuffle') shuffleArray(list);
    queue = { tracks: list, mode, index: 0 };
    const t = queue.tracks[0];
    playTrack(t.filename, t.title, t.uploader, { keepQueue: true });
  }
  window.playQueue = playQueue;

  function advanceQueue(dir = 1) {
    if (!queue) return;
    queue.index += dir;
    if (queue.index >= queue.tracks.length) {
      queue.index = 0;
      if (queue.mode === 'shuffle') shuffleArray(queue.tracks);
    } else if (queue.index < 0) {
      queue.index = queue.tracks.length - 1;
    }
    const t = queue.tracks[queue.index];
    playTrack(t.filename, t.title, t.uploader, { keepQueue: true });
  }

  function changeTrack(dir) {
    if (readOnlyMode) {
      postJSON(dir > 0 ? '/controls/media/next' : '/controls/media/prev', {})
        .then(() => setTimeout(checkIdleNowPlaying, 300));
      return;
    }
    if (queue) { advanceQueue(dir); return; }
    if (!current || !window.library.length) return;
    const idx = window.library.findIndex(t => t.filename === current.filename);
    const nextIdx = idx === -1 ? 0 : (idx + dir + window.library.length) % window.library.length;
    const t = window.library[nextIdx];
    playTrack(t.filename, t.title, t.uploader);
  }
  window.nextTrack = () => changeTrack(1);
  window.prevTrack = () => changeTrack(-1);

  // --- Seek / Volume ---

  seekbar.addEventListener('input', () => { seeking = true; });
  seekbar.addEventListener('change', () => {
    const pos = Number(seekbar.value);
    if (!readOnlyMode) {
      if (outputMode === 'laptop' || outputMode === 'both') postJSON('/media/music/api/seek', { position: pos });
      if (audio && (outputMode === 'phone' || outputMode === 'both')) audio.currentTime = pos;
    }
    seeking = false;
  });

  const volumeEl = document.getElementById('np-volume');
  if (volumeEl) volumeEl.addEventListener('input', e => {
    const val = Number(e.target.value);
    if (outputMode === 'laptop' || outputMode === 'both') postJSON('/media/music/api/volume', { value: val });
    if (audio && (outputMode === 'phone' || outputMode === 'both')) audio.volume = val / 100;
  });

  // --- Output selection ---

  async function setOutput(mode) {
    const previousMode = outputMode;
    outputMode = mode;
    document.querySelectorAll('#output-select button').forEach(b => {
      b.classList.toggle('is-active', b.dataset.output === mode);
    });
    if (!current) return;

    const wasLaptop = previousMode === 'laptop' || previousMode === 'both';
    const wasPhone = previousMode === 'phone' || previousMode === 'both';
    const nowLaptop = mode === 'laptop' || mode === 'both';
    const nowPhone = mode === 'phone' || mode === 'both';
    if (wasLaptop === nowLaptop && wasPhone === nowPhone) return;

    let position = audio ? (audio.currentTime || 0) : 0;
    let playing = audio ? !audio.paused : false;
    if (wasLaptop) {
      try {
        const res = await fetch('/media/music/api/status');
        const s = await res.json();
        if (s.filename) { position = s.position || 0; playing = !!s.playing; }
      } catch (err) { /* laptop unreachable, fall back to phone's clock */ }
    }

    if (wasLaptop && !nowLaptop) { await postJSON('/media/music/api/stop', {}); stopStatusPolling(); }
    if (audio && wasPhone && !nowPhone) audio.pause();

    if (nowLaptop && !wasLaptop) {
      await postJSON('/media/music/api/play', { filename: current.filename, title: current.title });
      await postJSON('/media/music/api/seek', { position });
      if (!playing) await postJSON('/media/music/api/pause', {});
      startStatusPolling();
    }
    if (audio && nowPhone && !wasPhone) {
      audio.src = '/media/music/stream/' + encodeURIComponent(current.filename);
      audio.currentTime = position;
      if (playing) audio.play().catch(() => {});
    }
  }
  window.setOutput = setOutput;

  // --- Laptop status polling (drives the seek bar + syncs title
  //     if another device changed the track on the laptop) ---

  function startStatusPolling() {
    stopStatusPolling();
    statusTimer = setInterval(pollStatus, 1000);
    pollStatus();
  }
  function stopStatusPolling() {
    if (statusTimer) clearInterval(statusTimer);
    statusTimer = null;
  }
  async function pollStatus() {
    if (outputMode === 'phone') return;
    try {
      const res = await fetch('/media/music/api/status');
      const s = await res.json();
      if (!s.filename) {
        // Our own mpv instance has nothing loaded anymore (track ended,
        // stopped elsewhere, or preempted by external media starting) —
        // stop polling and let the idle watcher pick up whatever's now
        // playing on the laptop generally. If 'both' output mode had a
        // phone-side copy going too, stop that in lockstep.
        current = null;
        stopStatusPolling();
        if (audio && !audio.paused) {
          audio.pause();
          audio.removeAttribute('src');
          audio.load();
        }
        if (queue) {
          // Mid-playlist: was this the track naturally finishing (in
          // which case we should play the next one), or did external
          // media start and preempt us (in which case it now owns the
          // display and the queue should stop)? Ask now_playing.
          try {
            const res2 = await fetch('/media/music/api/now_playing');
            const np = await res2.json();
            if (np.source === 'laptop-media') { queue = null; applyNowPlaying(np); return; }
          } catch (err) { /* ignore, fall through to advancing */ }
          advanceQueue();
          return;
        }
        resetNowPlayingUI();
        checkIdleNowPlaying();
        return;
      }
      if (!current || current.filename !== s.filename) {
        // Another device changed the track — adopt it.
        const match = window.library.find(t => t.filename === s.filename);
        current = { filename: s.filename, title: s.title, uploader: match && match.uploader };
        document.getElementById('np-title').textContent = s.title || s.filename;
        document.getElementById('np-artist').textContent = (match && match.uploader) || '';
      }
      document.getElementById('np-toggle').innerHTML = s.playing ? '&#10074;&#10074;' : '&#9654;';
      if (!seeking) {
        if (s.duration) seekbar.max = Math.floor(s.duration);
        seekbar.value = Math.floor(s.position || 0);
        document.getElementById('np-position').textContent = fmtTime(s.position);
        document.getElementById('np-duration').textContent = fmtTime(s.duration);
      }
    } catch (err) { /* laptop unreachable, ignore */ }
  }

  if (audio) {
    audio.addEventListener('timeupdate', () => {
      if (outputMode !== 'phone' || seeking) return;
      seekbar.max = Math.floor(audio.duration || 0);
      seekbar.value = Math.floor(audio.currentTime || 0);
      document.getElementById('np-position').textContent = fmtTime(audio.currentTime);
      document.getElementById('np-duration').textContent = fmtTime(audio.duration);
    });
    audio.addEventListener('play', () => { document.getElementById('np-toggle').innerHTML = '&#10074;&#10074;'; });
    audio.addEventListener('pause', () => { document.getElementById('np-toggle').innerHTML = '&#9654;'; });
    audio.addEventListener('ended', () => {
      // 'both' mode is advanced by the laptop-side poll above instead,
      // to avoid double-advancing when both finish around the same time.
      if (queue && outputMode === 'phone') advanceQueue();
    });
  }

  // --- Restore on load + continuous idle sync ---

  function setReadOnlyMode(readOnly) {
    readOnlyMode = readOnly;
    seekbar.disabled = false; // seeking stays available; laptop-media just won't accept phone-side seeks
    const stopBtn = document.getElementById('np-stop');
    if (stopBtn) stopBtn.style.display = readOnly ? 'none' : '';
    document.querySelectorAll('#output-select button').forEach(b => { b.disabled = readOnly; });
  }

  function applyTransportState(s) {
    document.getElementById('np-toggle').innerHTML = s.playing ? '&#10074;&#10074;' : '&#9654;';
    if (s.duration) seekbar.max = Math.floor(s.duration);
    seekbar.value = Math.floor(s.position || 0);
    document.getElementById('np-position').textContent = fmtTime(s.position);
    document.getElementById('np-duration').textContent = fmtTime(s.duration);
  }

  function applyNowPlaying(s) {
    const downloadBtn = document.getElementById('np-download');

    if (s.source === 'music-tool') {
      current = { filename: s.filename, title: s.title };
      const match = window.library.find(t => t.filename === s.filename);
      document.getElementById('np-title').textContent = s.title || s.filename;
      document.getElementById('np-artist').textContent = (match && match.uploader) || '';
      if (downloadBtn) downloadBtn.style.display = 'none';
      setReadOnlyMode(false);
      applyTransportState(s);
      startStatusPolling();
      return;
    }

    if (s.source === 'laptop-media') {
      document.getElementById('np-title').textContent = s.title;
      document.getElementById('np-artist').textContent = [s.artist, s.album].filter(Boolean).join(' \u00b7 ');
      if (downloadBtn) {
        downloadBtn.style.display = '';
        downloadBtn.disabled = false;
        downloadBtn.textContent = 'Download to library';
      }
      setReadOnlyMode(true);
      applyTransportState(s);
      return;
    }

    if (downloadBtn) downloadBtn.style.display = 'none';
    setReadOnlyMode(false);
    resetNowPlayingUI();
  }

  async function downloadCurrentlyPlaying() {
    const btn = document.getElementById('np-download');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Downloading\u2026';
    try {
      const data = await postJSON('/media/music/api/download_current', {});
      if (data.status === 'error') {
        btn.disabled = false;
        btn.textContent = 'Download to library';
        alert(data.message || 'Download failed.');
        return;
      }
      btn.textContent = 'Downloaded \u2713';
      await loadLibrary();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Download to library';
      alert('Download failed (network error).');
    }
  }
  window.downloadCurrentlyPlaying = downloadCurrentlyPlaying;
  window.togglePlay = togglePlay;
  window.stopPlayback = stopPlayback;

  // Runs continuously — on every page with the player bar — so a
  // laptop-media track that starts after load still shows up, and so
  // every open tab/device notices changes made elsewhere. Backs off
  // on the 1s status poll while `current` is set (that already owns
  // the display), but keeps checking `now_playing` regardless so a
  // switch between "our track" and "general laptop media" is caught.
  function startIdleWatcher() {
    if (idleWatcher) return;
    idleWatcher = setInterval(checkIdleNowPlaying, 2000);
  }
  async function checkIdleNowPlaying() {
    try {
      const res = await fetch('/media/music/api/now_playing');
      // Always make this call, even while our own track owns the UI:
      // it's also how the backend learns whether laptop-media just
      // started, so it can preempt our track if so. But only *apply*
      // the result here when nothing of ours already owns the display
      // (the 1s /api/status poll in pollStatus() does that instead,
      // and will pick up the preemption within a second via its own
      // "filename disappeared" check).
      if (current && !readOnlyMode) return;
      const s = await res.json();
      applyNowPlaying(s);
    } catch (err) { /* laptop unreachable, ignore */ }
  }

  async function initFromStatus() {
    try {
      const res = await fetch('/media/music/api/now_playing');
      const s = await res.json();
      applyNowPlaying(s);
    } catch (err) { /* laptop unreachable on load, ignore */ }
    startIdleWatcher();
  }

  // --- Adjust page bottom padding to the player's real height, so
  //     it never covers content (height varies by breakpoint/state) ---
  function trackPlayerHeight() {
    const set = () => document.documentElement.style.setProperty('--player-h', bar.offsetHeight + 'px');
    set();
    if (window.ResizeObserver) new ResizeObserver(set).observe(bar);
    else window.addEventListener('resize', set);
  }

  document.getElementById('np-toggle').addEventListener('click', togglePlay);
  document.getElementById('np-next').addEventListener('click', () => changeTrack(1));
  document.getElementById('np-prev').addEventListener('click', () => changeTrack(-1));
  const stopBtnEl = document.getElementById('np-stop');
  if (stopBtnEl) stopBtnEl.addEventListener('click', stopPlayback);
  const downloadBtnEl = document.getElementById('np-download');
  if (downloadBtnEl) downloadBtnEl.addEventListener('click', downloadCurrentlyPlaying);
  document.querySelectorAll('#output-select button').forEach(b => {
    b.addEventListener('click', () => setOutput(b.dataset.output));
  });

  trackPlayerHeight();
  (async () => {
    await loadLibrary();
    await initFromStatus();
  })();
})();
