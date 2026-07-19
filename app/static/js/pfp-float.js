/* ------------------------------------------------------------
   FLOATING PFP — bouncing/spinning, draggable (mouse + touch),
   alpha-aware hitbox, throwable.

   This element lives OUTSIDE the sliding #track — it's its own
   independent thing in viewport space. It doesn't ride along
   with the home panel; instead it gets physically corralled by
   the home panel's edges as they sweep across the screen during
   the horizontal route transition, so it "stays put" for a beat
   and then gets pushed out of the way once the moving edge
   actually reaches it.
   ------------------------------------------------------------ */
(() => {
  const img = document.getElementById('floatPfp');
  const track = document.getElementById('track');
  const trackWrapper = document.querySelector('.rh-track-wrapper');
  if (!img || !track || !trackWrapper) return;

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- alpha map, so clicks on transparent pixels pass through ---- */
  let alphaData = null, alphaW = 0, alphaH = 0;
  const probe = new Image();
  probe.src = img.currentSrc || img.src;
  probe.onload = () => {
    try {
      const c = document.createElement('canvas');
      alphaW = c.width = probe.naturalWidth;
      alphaH = c.height = probe.naturalHeight;
      const ctx = c.getContext('2d');
      ctx.drawImage(probe, 0, 0);
      alphaData = ctx.getImageData(0, 0, alphaW, alphaH).data;
    } catch (e) {
      alphaData = null; // e.g. blocked canvas read; fall back to full box
    }
  };

  function isOpaqueAt(clientX, clientY) {
    if (!alphaData) return true;
    const rect = img.getBoundingClientRect();
    const nx = (clientX - rect.left) / rect.width;
    const ny = (clientY - rect.top) / rect.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return false;
    const px = Math.min(alphaW - 1, Math.max(0, Math.floor(nx * alphaW)));
    const py = Math.min(alphaH - 1, Math.max(0, Math.floor(ny * alphaH)));
    return alphaData[(py * alphaW + px) * 4 + 3] > 24;
  }

  /* ---- live read of the track's current slide offset ----
     Used to derive where the home panel's left/right edges
     currently sit in viewport (fixed-position) coordinates,
     including mid-transition values. */
  function trackShiftPx() {
    const t = getComputedStyle(track).transform;
    if (!t || t === 'none') return 0;
    try { return new DOMMatrixReadOnly(t).m41; } catch (e) { return 0; }
  }

  /* ---- state ---- */
  let x = 0, y = 0;              // top-left, viewport px (position: fixed)
  let vx = 55, vy = 35;          // px/s
  let angle = 0, angVel = 16;    // deg / deg-per-s
  let bobT = Math.random() * 100;
  let dragging = false, pointerId = null;
  let dragOffX = 0, dragOffY = 0;
  let lastPX = 0, lastPY = 0, lastPT = 0;
  let moveHistory = []; // rolling {t,x,y} samples for a sturdier throw read
  const THROW_STRENGTH = 2.6;  // overall multiplier on release velocity
  const THROW_WINDOW_MS = 90;  // how far back we look to judge "how fast" you threw it

  const size = () => img.offsetWidth || 120;
  const viewW = () => trackWrapper.clientWidth;
  const viewH = () => trackWrapper.clientHeight;

  /* ---- wall-hit ripple: reuses the same .rh-blob--cursor ripple
     look as the click-and-hold effect, just spawned already in its
     "released" state at the exact spot the pfp made contact, instead
     of at a pointer. A short debounce stops it from re-firing every
     single frame while the pfp is pinned against a sweeping wall. ---- */
  const glowLayer = document.querySelector('#homeApp .rh-grid-glow');
  let lastWallRippleT = 0;
  const WALL_RIPPLE_COOLDOWN = 260; // ms

  function spawnWallRipple(cx, cy) {
    if (reduceMotion || !glowLayer) return;
    const now = performance.now();
    if (now - lastWallRippleT < WALL_RIPPLE_COOLDOWN) return;
    lastWallRippleT = now;
    const blob = document.createElement('span');
    blob.className = 'rh-blob rh-blob--cursor is-releasing';
    blob.style.left = `${cx}px`;
    blob.style.top = `${cy}px`;
    glowLayer.appendChild(blob);
    blob.addEventListener('animationend', () => blob.remove(), { once: true });
    setTimeout(() => blob.remove(), 1400); // safety net, mirrors the click ripple
  }

  let wasOnScreen = true; // tracks visibility so we can catch the moment it leaves the screen
  let prevWallLeft = null, prevWallRight = null; // for measuring how fast the walls themselves sweep

  /* ---- entrance: the pfp starts at opacity:0 (see CSS) and stays
     hidden until the intro overlay + nav/track/footer reveal have
     finished, so it's the last thing to land rather than popping in
     alongside everything else. script.js fires 'rh:revealed' the
     moment that reveal kicks off; we wait a bit longer past that for
     its own transitions to actually settle, then fade/glitch the pfp
     in. A timeout fallback guarantees it shows up even if that event
     never arrives for some reason. ---- */
  const REVEAL_SETTLE_MS = 750; // ~ matches rh-reveal-track's transition + delay
  let entered = false;
  const spawnSound = new Audio('/static/sfx/spawn.mp3');
  spawnSound.volume = 0.6;
  function enterPfp() {
    if (entered) return;
    entered = true;
    img.classList.add('rh-pfp-enter');
    spawnSound.play().catch(() => {}); // ignore autoplay-policy rejections
  }
  document.addEventListener('rh:revealed', () => setTimeout(enterPfp, REVEAL_SETTLE_MS), { once: true });
  setTimeout(enterPfp, 5000);

  function scatterVelocity() {
    const dir = Math.random() * Math.PI * 2;
    const speed = 70 + Math.random() * 110;
    vx = Math.cos(dir) * speed;
    vy = Math.sin(dir) * speed;
    angVel = (Math.random() * 2 - 1) * 220;
  }

  function placeInitial() {
    const s = size();
    x = viewW() * 0.76 - s / 2;
    y = viewH() * 0.26 - s / 2;
  }
  requestAnimationFrame(placeInitial);

  window.addEventListener('resize', () => {
    const s = size();
    x = Math.min(Math.max(x, 0), Math.max(0, viewW() - s));
    y = Math.min(Math.max(y, 0), Math.max(0, viewH() - s));
  });

  function render() {
    img.style.transform = `translate3d(${x}px, ${y}px, 0) rotate(${angle}deg)`;
  }

  let lastT = performance.now();
  function tick(now) {
    const dt = Math.min(0.05, (now - lastT) / 1000);
    lastT = now;
    const s = size();
    const h = viewH();

    // the "home panel" box, live, in viewport coordinates — this is
    // what corrals the pfp; it only equals the full screen while idle
    // on home, and slides away during route transitions.
    const shift = trackShiftPx();
    const wallLeft = shift;
    const wallRight = shift + viewW();

    // how fast each wall itself is sweeping this frame (px/s) — a wall
    // mid-transition can move far faster than the pfp's own velocity,
    // so on contact we hand the pfp the wall's speed (plus a kick)
    // rather than just clamping its position frame after frame. That
    // way it actually leaves with real momentum once the wall stops,
    // instead of ending up glued exactly at the wall's final resting
    // spot (which, on the way back to home, was always x = 0).
    const wallLeftVel = prevWallLeft === null ? 0 : (wallLeft - prevWallLeft) / dt;
    const wallRightVel = prevWallRight === null ? 0 : (wallRight - prevWallRight) / dt;
    prevWallLeft = wallLeft;
    prevWallRight = wallRight;

    if (dragging) {
      // dragging still respects the walls — you can't drag it through
      // a panel edge that's mid-slide.
      if (x < wallLeft) x = wallLeft;
      if (x + s > wallRight) x = wallRight - s;
      if (y < 0) y = 0;
      if (y + s > h) y = h - s;
    } else if (!reduceMotion) {
      bobT += dt;
      x += vx * dt;
      y += vy * dt + Math.sin(bobT * 1.3) * 5 * dt;

      let hitLeft = false, hitRight = false, hitTop = false, hitBottom = false;

      if (x < wallLeft) {
        x = wallLeft;
        vx = Math.max(Math.abs(vx) * 0.82, wallLeftVel + 90);
        angVel = -angVel - 40;
        hitLeft = true;
      }
      if (x + s > wallRight) {
        x = wallRight - s;
        vx = Math.min(-Math.abs(vx) * 0.82, wallRightVel - 90);
        angVel = -angVel - 40;
        hitRight = true;
      }
      if (y < 0) { y = 0; vy = Math.abs(vy) * 0.88; hitTop = true; }
      if (y + s > h) { y = h - s; vy = -Math.abs(vy) * 0.88; hitBottom = true; }

      // corner hits get one ripple at the actual corner rather than
      // two overlapping edge ripples right next to each other.
      if (hitLeft && hitTop) spawnWallRipple(wallLeft, 0);
      else if (hitLeft && hitBottom) spawnWallRipple(wallLeft, h);
      else if (hitRight && hitTop) spawnWallRipple(wallRight, 0);
      else if (hitRight && hitBottom) spawnWallRipple(wallRight, h);
      else if (hitLeft) spawnWallRipple(wallLeft, y + s / 2);
      else if (hitRight) spawnWallRipple(wallRight, y + s / 2);
      else if (hitTop) spawnWallRipple(x + s / 2, 0);
      else if (hitBottom) spawnWallRipple(x + s / 2, h);

      const speed = Math.hypot(vx, vy);
      if (speed < 16) {
        // idle floor: never fully stalls
        const k = 16 / (speed || 1); vx *= k; vy *= k;
      } else if (speed > 150) {
        // above ambient bobbing speed (i.e. just thrown): let it fly,
        // just bleed off some energy each frame like air drag, rather
        // than snapping it straight back down to idle speed.
        const drag = Math.pow(0.35, dt);
        vx *= drag; vy *= drag;
      }
    }

    // rotation always keeps going — dragging included — carrying
    // whatever spin energy it currently has, gently settling toward
    // a calm ambient drift when nothing's throwing it around.
    if (!reduceMotion) {
      angle += angVel * dt;
      if (!dragging) {
        angVel += (Math.sign(angVel || 1) * 16 - angVel) * Math.min(1, dt * 0.6);
      }
    }

    // physics keeps running even while fully off-screen (e.g. parked
    // off the side during a non-home route) — nothing above this point
    // is gated on visibility. The moment it goes *completely* off-screen,
    // give it a fresh random direction/speed so it keeps drifting around
    // dynamically back there; no teleporting or respawning once it
    // comes back into view — it's just wherever that motion left it.
    const isOnScreen = !(x + s <= 0 || x >= viewW() || y + s <= 0 || y >= viewH());
    if (!isOnScreen && wasOnScreen && !dragging) scatterVelocity();
    wasOnScreen = isOnScreen;

    render();
    requestAnimationFrame(tick);
  }
  requestAnimationFrame((t) => { lastT = t; requestAnimationFrame(tick); });

  /* ---- drag (unified pointer events: mouse + touch) ---- */
  img.addEventListener('pointerdown', (e) => {
    if (!isOpaqueAt(e.clientX, e.clientY)) return;
    e.preventDefault();
    dragging = true;
    pointerId = e.pointerId;
    img.setPointerCapture(pointerId);
    img.classList.add('is-dragging');
    dragOffX = e.clientX - x;
    dragOffY = e.clientY - y;
    lastPX = e.clientX; lastPY = e.clientY; lastPT = performance.now();
    vx = 0; vy = 0;
    moveHistory = [{ t: lastPT, x: e.clientX, y: e.clientY }];
  });

  img.addEventListener('pointermove', (e) => {
    if (!dragging || e.pointerId !== pointerId) return;
    const now = performance.now();
    const dt = Math.max(1, now - lastPT);
    // instantaneous drag velocity — used for the live spin feel.
    vx = (e.clientX - lastPX) / dt * 1000;
    vy = (e.clientY - lastPY) / dt * 1000;
    lastPX = e.clientX; lastPY = e.clientY; lastPT = now;
    x = e.clientX - dragOffX;
    y = e.clientY - dragOffY;
    // dragging also imparts spin — swing it around and it picks up
    // rotational energy proportional to how you're moving it.
    angVel = angVel * 0.72 + vx * 0.045;

    // keep a short rolling history so the eventual throw is judged
    // by a real swing, not just one noisy last-frame delta.
    moveHistory.push({ t: now, x: e.clientX, y: e.clientY });
    while (moveHistory.length > 2 && now - moveHistory[0].t > THROW_WINDOW_MS) moveHistory.shift();
  });

  function endDrag(e) {
    if (!dragging || (pointerId !== null && e.pointerId !== pointerId)) return;
    dragging = false;
    img.classList.remove('is-dragging');
    try { img.releasePointerCapture(pointerId); } catch (_) {}
    pointerId = null;

    // the throw: velocity is read across the last ~90ms of movement
    // (not just the final delta) and boosted, so a real flick actually
    // sends it flying instead of barely nudging it.
    let tvx = vx, tvy = vy;
    if (moveHistory.length >= 2) {
      const first = moveHistory[0];
      const last = moveHistory[moveHistory.length - 1];
      const dt = Math.max(1, last.t - first.t);
      tvx = (last.x - first.x) / dt * 1000;
      tvy = (last.y - first.y) / dt * 1000;
    }
    vx = tvx * THROW_STRENGTH;
    vy = tvy * THROW_STRENGTH;

    const speed = Math.hypot(vx, vy), maxV = 2200;
    if (speed > maxV) { const k = maxV / speed; vx *= k; vy *= k; }
    angVel = Math.max(-480, Math.min(480, angVel + vx * 0.12));
    moveHistory = [];
  }
  img.addEventListener('pointerup', endDrag);
  img.addEventListener('pointercancel', endDrag);
  img.addEventListener('dragstart', (e) => e.preventDefault());
  // On touch, a long, mostly-still press (e.g. lining up a drag before
  // moving) can trigger the browser's native "save image" / callout
  // menu, which fires pointercancel and makes it look like the drag
  // was dropped early even though the finger never lifted. CSS
  // (-webkit-touch-callout: none) handles most of this; blocking the
  // menu event itself is the fallback for browsers that still show it.
  img.addEventListener('contextmenu', (e) => e.preventDefault());
})();
