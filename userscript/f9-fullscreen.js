// ==UserScript==
// @name         雀魂 F9 全屏切换
// @namespace    adlkt
// @version      1.0.0
// @description  在雀魂麻将 (game.maj-soul.com) 页面按 F9 切换全屏，再按一次退出
// @match        https://game.maj-soul.com/1/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  function isFullscreen() {
    return Boolean(
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.mozFullScreenElement ||
      document.msFullscreenElement
    );
  }

  function enterFullscreen() {
    const el = document.documentElement;
    const p =
      el.requestFullscreen?.() ??
      el.webkitRequestFullscreen?.() ??
      el.msRequestFullscreen?.() ??
      el.mozRequestFullScreen?.();
    // 某些浏览器会拒绝请求，吞掉 rejection 避免刷屏报错
    p?.catch?.(() => {});
  }

  function exitFullscreen() {
    const p =
      document.exitFullscreen?.() ??
      document.webkitExitFullscreen?.() ??
      document.msExitFullscreen?.() ??
      document.mozCancelFullScreen?.();
    p?.catch?.(() => {});
  }

  // capture 阶段监听，防止游戏页自身的事件处理拦截 F9
  window.addEventListener(
    'keydown',
    (e) => {
      if (e.key !== 'F9' && e.code !== 'F9') return;
      e.preventDefault();
      e.stopPropagation();
      if (isFullscreen()) exitFullscreen();
      else enterFullscreen();
    },
    true
  );
})();
