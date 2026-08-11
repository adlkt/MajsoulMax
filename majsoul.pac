function FindProxyForURL(url, host) {
    // 雀魂游戏域名 → mitmproxy；其余流量直连
    if (
        dnsDomainIs(host, "maj-soul.com") ||
        shExpMatch(host, "*.maj-soul.com") ||
        dnsDomainIs(host, "mahjongsoul.com") ||
        shExpMatch(host, "*.mahjongsoul.com") ||
        dnsDomainIs(host, "catmjstudio.com") ||
        shExpMatch(host, "*.catmjstudio.com") ||
        shExpMatch(host, "*.yo-star.com")
    ) {
        return "PROXY 127.0.0.1:23410";
    }
    return "DIRECT";
}
