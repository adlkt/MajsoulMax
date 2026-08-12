// ==UserScript==
// @name         雀魂 F9 全屏切换
// @namespace    adlkt
// @version      1.2.1
// @description  在雀魂麻将页面按 F9 切换全屏（实现参考 VueUse useFullscreen）
// @match        https://game.maj-soul.com/1/*
// @match        https://mahjongsoul.game.yo-star.com/1/*
// @match        https://game.mahjongsoul.com/1/*
// @run-at       document-start
// @grant        none
// @noframes
// ==/UserScript==

(function () {
  'use strict';

  const VERSION = '1.2.1';
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

  // 目标元素（html）当前是否全屏
  function targetIsFullscreen() {
    const el = doc[fullscreenElementMethod];
    return Boolean(el) && el === target();
  }

  // 文档里是否有任何元素在全屏
  function anyFullscreen() {
    return Boolean(doc[fullscreenElementMethod]);
  }

  // Chrome 全屏状态机偶发卡死：请求会无限 pending 不 resolve。
  // 加超时保护，超时给出明确提示（重启浏览器是唯一解）。
  function withTimeout(p, hint) {
    return Promise.race([
      Promise.resolve(p),
      new Promise((_, reject) => setTimeout(() => reject(new Error(hint)), 5000)),
    ]);
  }

  async function exit() {
    if (!anyFullscreen()) return;
    try {
      if (exitMethod in doc) await withTimeout(doc[exitMethod](), '退出全屏超时——Chrome 全屏状态可能卡死，建议重启浏览器');
      else await withTimeout(target()[exitMethod](), '退出全屏超时——Chrome 全屏状态可能卡死，建议重启浏览器');
    } catch (err) {
      console.warn('[f9-fullscreen] 退出全屏失败:', err);
    }
  }

  async function enter() {
    if (!isSupported()) {
      console.warn('[f9-fullscreen] document.fullscreenEnabled === false，浏览器/页面禁止了全屏 API');
      return;
    }
    if (targetIsFullscreen()) return;
    if (anyFullscreen()) await exit(); // 有别的元素全屏（如游戏内 canvas），先清场再进
    try {
      await withTimeout(target()[requestMethod](), '进入全屏超时——Chrome 全屏状态可能卡死，建议重启浏览器');
    } catch (err) {
      console.warn('[f9-fullscreen] 进入全屏失败:', err);
    }
  }

  // 状态由 fullscreenchange 事件驱动，始终与浏览器同步
  let isFullscreen = false;
  function sync() {
    isFullscreen = targetIsFullscreen();
  }
  doc.addEventListener('fullscreenchange', sync, true);
  doc.addEventListener('webkitfullscreenchange', sync, true);
  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', sync);
  } else {
    sync();
  }

  async function toggle() {
    if (isFullscreen) await exit();
    else await enter();
  }

  window.addEventListener('keydown', (e) => {
    if (e.key !== 'F9' && e.code !== 'F9') return;
    console.log('[f9-fullscreen] F9 pressed, repeat =', e.repeat);
    if (e.repeat) return; // 忽略长按自动重复
    e.preventDefault();
    e.stopPropagation();
    toggle();
  }, true);
})();
