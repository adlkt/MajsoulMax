// ==UserScript==
// @name         雀魂 F9 全屏切换
// @namespace    adlkt
// @version      1.4.0
// @description  在雀魂麻将页面按 F9 切换全屏（实现参考 VueUse useFullscreen）；v1.4：补 game.maj-soul.net 域名、退出稳定窗口防竞态、进入失败自动重试、状态机自愈、诊断日志
// @match        https://game.maj-soul.com/1/*
// @match        https://game.maj-soul.net/1/*
// @match        https://mahjongsoul.game.yo-star.com/1/*
// @match        https://game.mahjongsoul.com/1/*
// @run-at       document-start
// @grant        none
// @noframes
// ==/UserScript==

(function () {
  'use strict';

  const VERSION = '1.4.0';
  // 详细诊断：控制台执行 localStorage.f9debug='1' 后刷新页面开启；默认只打每次切换结果
  const DEBUG = (() => {
    try { return localStorage.getItem('f9debug') === '1'; } catch { return false; }
  })();
  const log = (...a) => console.info('[f9]', ...a);
  const dbg = (...a) => { if (DEBUG) console.debug('[f9]', ...a); };

  log(`v${VERSION} loaded @`, location.href);

  // ---- API 探测链（移植自 VueUse useFullscreen）----
  const requestMethods = [
    'requestFullscreen', 'webkitRequestFullscreen', 'webkitEnterFullscreen',
    'webkitEnterFullScreen', 'webkitRequestFullScreen', 'mozRequestFullScreen',
    'msRequestFullscreen',
  ];
  const exitMethods = [
    'exitFullscreen', 'webkitExitFullscreen', 'webkitExitFullScreen',
    'webkitCancelFullScreen', 'mozCancelFullScreen', 'msExitFullscreen',
  ];
  const fullscreenElementMethods = [
    'fullscreenElement', 'webkitFullscreenElement', 'mozFullScreenElement',
    'msFullscreenElement',
  ];

  const doc = document;
  const target = () => doc.documentElement;

  function find(methods) {
    for (const m of methods) {
      if (m in doc || m in target()) return m;
    }
    return undefined;
  }

  const requestMethod = find(requestMethods);
  const exitMethod = find(exitMethods);
  const fullscreenElementMethod = find(fullscreenElementMethods);

  if (!requestMethod || !exitMethod || !fullscreenElementMethod) {
    console.warn('[f9-fullscreen] 环境不支持 Fullscreen API:', {
      requestMethod, exitMethod, fullscreenElementMethod,
    });
    return;
  }

  // fullscreenEnabled === false = 浏览器/页面策略禁止全屏（如受限 iframe）
  const isSupported = () => doc.fullscreenEnabled !== false;

  // 文档里是否有任何元素在全屏（实时查询，不依赖事件缓存）
  function anyFullscreen() {
    return Boolean(doc[fullscreenElementMethod]);
  }

  // 目标元素（html）当前是否全屏
  function targetIsFullscreen() {
    const el = doc[fullscreenElementMethod];
    return Boolean(el) && el === target();
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // 轮询等待谓词成立，最多 ms；返回是否成功。用于确认全屏真正生效/退出。
  function waitUntil(predicate, ms, interval = 100) {
    return new Promise((resolve) => {
      const start = Date.now();
      (function check() {
        if (predicate()) return resolve(true);
        if (Date.now() - start >= ms) return resolve(false);
        setTimeout(check, interval);
      })();
    });
  }

  // 等待 fullscreen 调用 settle；超时返回 TIMED_OUT，永不 throw（防 unhandled rejection）
  const TIMED_OUT = Symbol('f9-fullscreen-timeout');
  function withTimeout(p, ms = 3000) {
    return new Promise((resolve) => {
      let done = false;
      const timer = setTimeout(() => {
        if (!done) { done = true; resolve(TIMED_OUT); }
      }, ms);
      Promise.resolve(p).then(
        () => { if (!done) { done = true; clearTimeout(timer); resolve('ok'); } },
        (err) => {
          if (!done) { done = true; clearTimeout(timer); resolve('error'); }
          console.warn('[f9-fullscreen] fullscreen 调用被拒绝:', err && err.message || err);
        },
      );
    });
  }

  // 绕过 anyFullscreen() 检查，强制调一次 exit。注意：Chrome 状态机卡在
  // EnteringFullscreen 时 exit/request 都会被静默忽略，所以这只是尽力而为，
  // 真正的自愈靠重试循环 + 等待让状态机自然收敛。
  function forceExit() {
    try {
      if (!exitMethod) return;
      const p = exitMethod in doc ? doc[exitMethod]() : target()[exitMethod]();
      if (p && p.catch) p.catch(() => {});
    } catch (e) {
      console.warn('[f9-fullscreen] forceExit 失败:', e);
    }
  }

  // 轻量提示（@grant none 环境，不依赖任何 API）
  function toast(msg) {
    try {
      const div = document.createElement('div');
      div.textContent = msg;
      div.style.cssText =
        'position:fixed;top:16px;left:50%;transform:translateX(-50%);' +
        'z-index:2147483647;background:rgba(0,0,0,.82);color:#fff;' +
        'padding:10px 18px;border-radius:8px;font:13px/1.5 sans-serif;' +
        'pointer-events:none;transition:opacity .3s;';
      (doc.body || doc.documentElement).appendChild(div);
      setTimeout(() => { div.style.opacity = '0'; setTimeout(() => div.remove(), 350); }, 2600);
    } catch { /* 忽略 */ }
  }

  // ---- 状态机 ----
  let toggling = false;   // 互斥锁：防快速连按 F9 并发 request/exit
  let failStreak = 0;     // 连续失败计数（第 2 次仍失败时提示刷新/重开标签页）
  let lastFsExit = 0;     // 上次"任何原因"退出全屏的时间戳（ESC/脚本/外部）

  const SETTLE_MS = 500;    // 退出过渡稳定窗口（防 1654512 类 enter/exit 竞态）
  const MAX_ATTEMPTS = 3;   // 进入全屏最大重试次数

  // 真实键盘事件（Chrome 要求用户手势，keydown 监听即手势来源）
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'F9' && e.code !== 'F9') return;
    if (e.repeat) return; // 忽略长按自动重复
    e.preventDefault();
    e.stopPropagation();
    toggle();
  }, true);

  // fullscreenchange：同步 lastFsExit（ESC/外部退出也在这里记录，enter 前等过渡完成）
  document.addEventListener('fullscreenchange', () => {
    if (!anyFullscreen()) lastFsExit = Date.now();
    dbg('fullscreenchange →', anyFullscreen() ? 'enter' : 'exit');
  }, true);

  async function exit() {
    if (!anyFullscreen()) return;
    dbg('exit: begin');
    const p = exitMethod in doc ? doc[exitMethod]() : target()[exitMethod]();
    const r = await withTimeout(p, 3000);
    const exited = r === 'ok' || !anyFullscreen() || await waitUntil(() => !anyFullscreen(), 2000);
    if (exited) {
      failStreak = 0;
      lastFsExit = Date.now();
      dbg('exit: ok');
      return;
    }
    // 退出卡住
    failStreak++;
    dbg('exit: stuck, forceExit + wait');
    forceExit();
    const ok = await waitUntil(() => !anyFullscreen(), 2000);
    if (ok) {
      failStreak = 0;
      lastFsExit = Date.now();
    } else {
      toast(failStreak >= 2 ? '全屏仍无法恢复，建议关闭标签页重新打开' : '退出全屏卡住，已尝试重置，请再按一次 F9');
    }
  }

  async function enter() {
    if (!isSupported()) {
      console.warn('[f9-fullscreen] document.fullscreenEnabled === false，浏览器/页面禁止了全屏 API');
      return;
    }

    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      dbg(`enter: attempt ${attempt + 1}/${MAX_ATTEMPTS}`);

      if (targetIsFullscreen()) { failStreak = 0; dbg('enter: already in'); return; }

      // 有别的元素全屏（如游戏内 canvas）先清场
      if (anyFullscreen()) {
        await exit();
        await sleep(SETTLE_MS);
      }

      // 上次退出全屏（ESC/脚本/外部）后需等退出过渡完成，否则 request 会被
      // Chrome 静默吞掉或进入"假成功"状态（fullscreenchange 触发但没真全屏）
      const sinceExit = Date.now() - lastFsExit;
      if (lastFsExit > 0 && sinceExit < SETTLE_MS) {
        dbg(`enter: settle wait ${SETTLE_MS - sinceExit}ms`);
        await sleep(SETTLE_MS - sinceExit);
      }

      // 重试前强制重置一次状态机（Chrome 卡死时是 no-op，尽力而为）
      if (attempt > 0) {
        forceExit();
        await sleep(400);
      }

      const r = await withTimeout(target()[requestMethod](), 3000);
      // promise resolve 不代表 fullscreenElement 已就位，轮询确认真正进入
      const entered = (r === 'ok' || targetIsFullscreen()) &&
        await waitUntil(targetIsFullscreen, 1000);

      if (entered) {
        failStreak = 0;
        dbg(`enter: ok (attempt ${attempt + 1})`);
        return;
      }

      failStreak++;
      dbg(`enter: failed attempt ${attempt + 1} (${r === TIMED_OUT ? 'timeout' : r})`);
      if (attempt < MAX_ATTEMPTS - 1) {
        forceExit();
        await sleep(400);
      }
    }

    // 全部重试失败 → 状态机大概率真卡死（Chrome 进程级，页面侧无法强解）
    toast(failStreak >= 2 ? '全屏仍无法恢复，建议关闭标签页重新打开' : '全屏请求卡住，已尝试重置，请再按一次 F9');
    log('enter: gave up after', MAX_ATTEMPTS, 'attempts; anyFs =', anyFullscreen());
  }

  async function toggle() {
    if (toggling) return;
    toggling = true;
    const started = Date.now();
    try {
      if (anyFullscreen()) { await exit(); log('toggle: exit,', Date.now() - started, 'ms'); }
      else { await enter(); log('toggle: enter,', Date.now() - started, 'ms'); }
    } finally {
      toggling = false;
    }
  }

  // Chrome bug mitigation：全屏请求 pending 时页面导航最容易锁死状态机（crbug 1131659 等）。
  // 页面卸载前尽力退出，从源头降低触发概率。
  window.addEventListener('pagehide', () => {
    if (anyFullscreen()) forceExit();
  });
})();
