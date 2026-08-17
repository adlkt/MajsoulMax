function main(config) {
    // 你不同机场的自动选择名称不一样就修改或者新增
    const autoGroupName = (() => {
        if (config['proxy-groups'].some(g => g.name === '自动选择')) {
            return '自动选择';
        }
        if (config['proxy-groups'].some(g => g.name === '♻️自动选择')) {
            return '♻️自动选择';
        }
        return 'DIRECT';
    })();

    config.proxies.push({
        name: 'MajsoulMax',
        type: 'http',
        server: '127.0.0.1',
        port: 23410,
        tls: true,
        // 本地回环节点，跳过证书校验：否则 Clash 内核连 mitmproxy 时
        // 会因不信任 mitmproxy 的 CA 证书导致 TLS handshake failed
        'skip-cert-verify': true,
    });

    const fallbackProxies = ['MajsoulMax'];
    if (config['proxy-groups'].some(g => g.name === '自动选择')) {
        fallbackProxies.push('自动选择');
    }
    if (config['proxy-groups'].some(g => g.name === '♻️自动选择')) {
        fallbackProxies.push('♻️自动选择');
    }
    fallbackProxies.push('DIRECT');

    config['proxy-groups'].push({
        name: '雀魂Max-故障转移',
        type: 'fallback',
        proxies: fallbackProxies,
        url: 'http://www.gstatic.com/generate_204',
        interval: 30,
        icon: 'https://www.maj-soul.com/homepage/img/logotaiwan.png',
    });

    const selectProxies = [
        '雀魂Max-故障转移',
        'MajsoulMax',
    ];
    if (config['proxy-groups'].some(g => g.name === '自动选择')) {
        selectProxies.push('自动选择');
    }
    if (config['proxy-groups'].some(g => g.name === '♻️自动选择')) {
        selectProxies.push('♻️自动选择');
    }
    selectProxies.push('DIRECT');

    config['proxy-groups'].push({
        name: '🀄 雀魂麻将',
        type: 'select',
        proxies: selectProxies,
        icon: 'https://www.maj-soul.com/homepage/img/logotaiwan.png',
    });

    const bypass = [
        `AND, ((OR, ((PROCESS-NAME-REGEX, python.*?),(PROCESS-NAME, MajsoulMax.exe))), (OR, ((PROCESS-NAME,Jantama_MahjongSoul.exe),(PROCESS-NAME,雀魂麻將.exe),(DOMAIN-KEYWORD, majsoul), (DOMAIN-KEYWORD, maj-soul), (DOMAIN-KEYWORD, mahjongsoul), (DOMAIN-KEYWORD, catmjstudio)))), ${autoGroupName}`,
    ];

    const clientRules = ['PROCESS-NAME,Jantama_MahjongSoul.exe,🀄 雀魂麻将', 'PROCESS-NAME,雀魂麻將.exe,🀄 雀魂麻将'];

    const webRules = [
        'DOMAIN-KEYWORD,majsoul,🀄 雀魂麻将',
        'DOMAIN-KEYWORD,maj-soul,🀄 雀魂麻将',
        'DOMAIN-KEYWORD,mahjongsoul,🀄 雀魂麻将',
        'DOMAIN-KEYWORD,catmjstudio,🀄 雀魂麻将',
    ];

    config.rules.unshift(...bypass, ...clientRules, ...webRules);
    return config;
}
