function main(config) {
  config.proxies.push({
    name: "MajsoulMax",
    type: "http",
    server: "127.0.0.1",
    port: 23410,
    tls: false,
  });

  config["proxy-groups"].push({
    name: "🀄 雀魂麻将",
    type: "select",
    proxies: ["DIRECT", "MajsoulMax"],
  });

  // 避免回环：Python 进程直连
  const bypass = [
    "AND, ((OR, ((PROCESS-NAME-REGEX, python.*?),(PROCESS-NAME, MajsoulMax.exe))), (OR, ((PROCESS-NAME,Jantama_MahjongSoul.exe),(PROCESS-NAME,雀魂麻將.exe),(DOMAIN-KEYWORD, majsoul), (DOMAIN-KEYWORD, maj-soul), (DOMAIN-KEYWORD, mahjongsoul), (DOMAIN-KEYWORD, catmjstudio)))), DIRECT",
  ];

  // 客户端 / Steam
  const clientRules = [
    "PROCESS-NAME,Jantama_MahjongSoul.exe,🀄 雀魂麻将",
    "PROCESS-NAME,雀魂麻將.exe,🀄 雀魂麻将",
  ];

  // 网页版
  const webRules = [
    "DOMAIN-KEYWORD,majsoul,🀄 雀魂麻将",
    "DOMAIN-KEYWORD,maj-soul,🀄 雀魂麻将",
    "DOMAIN-KEYWORD,mahjongsoul,🀄 雀魂麻将",
    "DOMAIN-KEYWORD,catmjstudio,🀄 雀魂麻将",
  ];

  config.rules.unshift(...bypass, ...clientRules, ...webRules);
  return config;
}
