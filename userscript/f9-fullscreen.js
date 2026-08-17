// ==UserScript==
// @name         雀魂 F9 全屏切换
// @namespace    adlkt
// @version      1.3.0
// @description  在雀魂麻将页面按 F9 切换全屏（实现参考 VueUse useFullscreen）；含 Chrome 全屏状态机卡死自愈
// @match        https://game.maj-soul.com/1/*
// @match        https://mahjongsoul.game.yo-star.com/1/*
// @match        https://game.mahjongsoul.com/1/*
// @run-at       document-start
// @grant        none
// @noframes
// ==/UserScript==

(function () {
  'use strict';

  const VERSION = '1.3.0';
  console.log(`[f9-fullscreen] v${VERSION} loaded @`, location.href);

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

  // 等待 fullscreen 调用 settle；超时返回 TIMED_OUT，永不 throw（防 unhandled rejection）
  const TIMED_OUT = Symbol('f9-fullscreen-timeout');
  function withTimeout(p, ms = 5000) {
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

  // 绕过 anyFullscreen() 检查，强制调一次 exitFullscreen。
  // Chrome 已知 bug：全屏请求 pending 时页面导航/reload 会让状态机锁死，
  // 此时 fullscreenElement 可能已为 null，但 exitFullscreen 仍能重置状态机。
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

  // 上一次请求超时未恢复 → 下一次进入前先强制重置状态机
  let needsReset = false;
  // 连续自愈失败计数：第 2 次仍失败时给出"重启浏览器"终态提示
  let failStreak = 0;

  async function exit() {
    if (!anyFullscreen()) return;
    const p = exitMethod in doc ? doc[exitMethod]() : target()[exitMethod]();
    const r = await withTimeout(p);
    if (r === TIMED_OUT && anyFullscreen()) {
      console.warn('[f9-fullscreen] 退出全屏超时，尝试强制重置状态机');
      failStreak++;
      needsReset = true;
      forceExit();
      toast(failStreak >= 2 ? '全屏仍无法恢复，建议重启浏览器' : '退出全屏卡住，已尝试重置，请再按一次 F9');
    } else {
      failStreak = 0;
    }
  }

  async function enter() {
    if (!isSupported()) {
      console.warn('[f9-fullscreen] document.fullscreenEnabled === false，浏览器/页面禁止了全屏 API');
      return;
    }
    if (targetIsFullscreen()) return;
    if (anyFullscreen()) await exit(); // 有别的元素全屏（如游戏内 canvas），先清场再进
    if (needsReset) {
      needsReset = false;
      forceExit();
      await new Promise((r) => setTimeout(r, 150)); // 给 Chrome 状态机一点重置时间
    }
    const r = await withTimeout(target()[requestMethod]());
    if (r === TIMED_OUT) {
      if (targetIsFullscreen()) { failStreak = 0; return; } // 实际已进入，promise 没 settle 而已
      console.warn('[f9-fullscreen] 进入全屏超时——Chrome 状态机疑似卡死，尝试重置');
      failStreak++;
      needsReset = true;
      forceExit();
      toast(failStreak >= 2 ? '全屏仍无法恢复，建议重启浏览器' : '全屏请求卡住，已尝试重置，请再按一次 F9');
    } else {
      failStreak = 0;
    }
  }

  // 互斥锁：防快速连按 F9 导致并发 request/exit 把状态机搞乱
  let toggling = false;
  async function toggle() {
    if (toggling) return;
    toggling = true;
    try {
      // 决策用实时 DOM 查询，不依赖事件缓存（fullscreenchange 偶发丢失）
      if (anyFullscreen()) await exit();
      else await enter();
    } finally {
      toggling = false;
    }
  }

  window.addEventListener('keydown', (e) => {
    if (e.key !== 'F9' && e.code !== 'F9') return;
    if (e.repeat) return; // 忽略长按自动重复
    e.preventDefault();
    e.stopPropagation();
    toggle();
  }, true);

  // Chrome bug mitigation：全屏中页面 reload/导航最容易锁死状态机（crbug 1131659 等）。
  // 页面卸载前主动退全屏，从源头降低触发概率。
  window.addEventListener('pagehide', () => {
    if (anyFullscreen()) forceExit();
  });
})();
