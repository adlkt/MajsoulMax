# 雀魂 MAX

雀魂解锁全角色、皮肤、装扮等，基于 [mitmproxy](https://github.com/mitmproxy/mitmproxy) 的中间人攻击方式，支持网页版和客户端 / Steam 端。

同时支持将雀魂的牌局发到 [日本麻将助手 mahjong-helper](https://github.com/EndlessCheng/mahjong-helper)，不支持牌谱分析。

本工具完全免费、开源，如果您为此付费，说明您被骗了！

## 🧭 当前雀魂各服版本（实时更新）

![CHINESE](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fgame.maj-soul.com%2F1%2Fversion.json&label=CHINESE&query=$.version&color=FF8C00&logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAA7EAAAOxAGVKw4bAAACsklEQVQ4ja2Tf0zMcRjHX9/7Ud0l59RCFssWmemGom5mNysbLb+GuM2G8mOMCGu0rD9aNuRHymxnNqbGqcwMG1lrRLmkRXOESoit311X1/34+MO37YY/vf96Pu89z+f5fJ73+5H4G1nAWWAPkAzoZL4LeAiU+SdLfrESKAZOAzeAVpl3AiogABgD5gImwPNn5yYgDngAXANKgZbbFw+J+jsnBdAJvA8KUNnNqUYBaP2LrwFXgQrAAtjmzAwfFG23RHtNkUhNinMaYiJ7gI6c3SkeoA4Q/l+oAdqB/mPpSVsLTu3US6FpXwDF9nVL9RmbVwSHaCTcPiV5xZUj96oaPsp1lSpg/vSwENdhc+KGyHCdtmvIKxYkZA51PyucUf36Kxv3n+uKmBqqWGVapPGM9JG5KUFzr6ohWJ7NAQnIBmI1geoge/mh9f29fdR+HPZGTZ2kmBwRKRmiI3jywi6Mi2ZL+oXbPztsRbOiV+b2dnUPdAIxKmBKmE4b8qgwLZUxF0XWl+4Rj9LF4hiNVxGkvPGuQxgXRkt371f7ANWrNx84l71Jv/mopRMYVAE/50TqjZ9+OCi50+i+cnytOj79yvDwqMtRaUnR2Vvs0r7cy85qW2s3oG77Nugzxc1UAG5gIrJ0pUBFaU6KAL5PC9P1lOWbReaWZaOXcs2eoaarwmErEsD36yczPG+tBwXQCAyMy/gcsALNQFNZvlkAn0ae5ouHJXt98fOi+svPZIhtqxOd9ttZotayS8hS5qnkC6xALBBoWhA1wdnf7QUCghRuQrWSlGQI11Q+fuk4f2TNhJp6OxesdX3AEiDB30x1QEvBjqVe+XnNQGN6imFsoOqEuHlijVApFe2ATbZxqL+RxmEBlgOjgE/mBOAC1PLZAIz74J9IloczCgzLcScwxO8N/b/4BZ4sCAP6Ouu4AAAAAElFTkSuQmCC&logoWidth=16) ![ENGLISH](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fmahjongsoul.game.yo-star.com%2Fversion.json&label=ENGLISH&query=$.version&color=FF8C00&logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAA7EAAAOxAGVKw4bAAADT0lEQVQ4jUXN2WtcVQDA4d+520xmsbOkM5OYNJkak5hJNQtE2mCgkj6ILUVEoTSIG0KVgpT4oIjig4qi5k0U8cWttr5IoUGoFBrRSilN1DRdNBMbkzTNNklmJplz7tx7fPDB7x/4BMDJZ0/kDw4fznquj1/1AM3Ia5/hyQpVDQDzi7OkExl2ptLUJOKcuzbO2V8vCOv1x+s/MKans3LuIyIdRynd0ly7uoTcKpPt7mN2coKqlLRm2/B8jTYExcIa+1v28Ol7J7TIf9hRCaVigfDunQR2JHA3lxl+qYxhaBKpDCuLC3QPPgJas3j9KoZpQjhMOl1H+K4Y1sJs0agrCUztM/zxGMeH2gjYEaSSzM3O4FgO4+dGEQLC4Si1u5qRrqK0WUQrhTW3IrmnM45lC159vp1kMoowobauntvzc9i2hVKKUDiMcl0W/84jXUm5JowhQIzk7leTRW0fGfA4m0/QfsegIRpgNKDJZOqZmvmdvs5u1gvbuK6ivFXGlRLbMBGAtb5hkAraXPzRZSkh6acGUXbZdMu8eWyIny63MDVxk3+W5onVxHBxaWxuZGlhhYrcRjzduU/llGl3KY0SJnlHcysTx/VW+eP6DZoMh0LI4eT571GywtTYz1y8fIWp8VlCdg1W0AkS3VYULJMzVolUIkMgaPHOyLv8cPo8k59/SeqhfRTXitS2t/DgkQYSjfWE1Rl+ufIXljAMqgEHp1RBahfTsdHKRxgWj77wBLmeNpr2H0AIF9Bow+C7T74l29fL1tgkVkVJNu7OMDjQT/TUN6B9TMNEBwJQkTQ/cB+itASRHSAEIGgtbhOrzbArlUYcasqpunjSLhTXiIaieNojFkvSmmvj2NvHwXbAMEEDAnTVhdI6zww+RyaewPJ9g9urKwRtC9NyuLO6zuDe3RSki7YCCK1B6/92IRCmBaEohmUQb85iKe2vVIqbdenaDOubCoFg8OWnyJ8eRXo+QeGDAIQBmOAp3nrxDfDgz/wMAuDeUFL31LewXZGEgkFeOfoYyT2NLE/cxGpvpuvQAbTvUcXgyd6H0VWH3q5+Jm78tiH431pnvCGeSzZxsKODvQM9mKEwSkne/+Ir5pYXiVgRpCoSCcY4NX3paw1D/wJx5WDqjkxa0wAAAABJRU5ErkJggg==&logoWidth=16) ![JAPANESE](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fgame.mahjongsoul.com%2Fversion.json&label=JAPANESE&query=$.version&color=FF8C00&logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAA7EAAAOxAGVKw4bAAADT0lEQVQ4jUXN2WtcVQDA4d+520xmsbOkM5OYNJkak5hJNQtE2mCgkj6ILUVEoTSIG0KVgpT4oIjig4qi5k0U8cWttr5IoUGoFBrRSilN1DRdNBMbkzTNNklmJplz7tx7fPDB7x/4BMDJZ0/kDw4fznquj1/1AM3Ia5/hyQpVDQDzi7OkExl2ptLUJOKcuzbO2V8vCOv1x+s/MKans3LuIyIdRynd0ly7uoTcKpPt7mN2coKqlLRm2/B8jTYExcIa+1v28Ol7J7TIf9hRCaVigfDunQR2JHA3lxl+qYxhaBKpDCuLC3QPPgJas3j9KoZpQjhMOl1H+K4Y1sJs0agrCUztM/zxGMeH2gjYEaSSzM3O4FgO4+dGEQLC4Si1u5qRrqK0WUQrhTW3IrmnM45lC159vp1kMoowobauntvzc9i2hVKKUDiMcl0W/84jXUm5JowhQIzk7leTRW0fGfA4m0/QfsegIRpgNKDJZOqZmvmdvs5u1gvbuK6ivFXGlRLbMBGAtb5hkAraXPzRZSkh6acGUXbZdMu8eWyIny63MDVxk3+W5onVxHBxaWxuZGlhhYrcRjzduU/llGl3KY0SJnlHcysTx/VW+eP6DZoMh0LI4eT571GywtTYz1y8fIWp8VlCdg1W0AkS3VYULJMzVolUIkMgaPHOyLv8cPo8k59/SeqhfRTXitS2t/DgkQYSjfWE1Rl+ufIXljAMqgEHp1RBahfTsdHKRxgWj77wBLmeNpr2H0AIF9Bow+C7T74l29fL1tgkVkVJNu7OMDjQT/TUN6B9TMNEBwJQkTQ/cB+itASRHSAEIGgtbhOrzbArlUYcasqpunjSLhTXiIaieNojFkvSmmvj2NvHwXbAMEEDAnTVhdI6zww+RyaewPJ9g9urKwRtC9NyuLO6zuDe3RSki7YCCK1B6/92IRCmBaEohmUQb85iKe2vVIqbdenaDOubCoFg8OWnyJ8eRXo+QeGDAIQBmOAp3nrxDfDgz/wMAuDeUFL31LewXZGEgkFeOfoYyT2NLE/cxGpvpuvQAbTvUcXgyd6H0VWH3q5+Jm78tiH431pnvCGeSzZxsKODvQM9mKEwSkne/+Ir5pYXiVgRpCoSCcY4NX3paw1D/wJx5WDqjkxa0wAAAABJRU5ErkJggg==&logoWidth=16)

## 📢 用前须知

注意：解锁人物仅在本地有效，别人还是只能看到你原来的角色，发表情也是原来角色的表情。比如使用新角色发第 3 个表情，实际上其他人看到的是原来角色的第 3 个表情。


## 🥰 当前功能

程序包含三部分：包括 `mod` 、 `helper` 和 `replace` ，可以说是 [雀魂 mod_plus](https://github.com/Avenshy/majsoul_mod_plus) 和 [mahjong-helper-majsoul-mitmproxy](https://github.com/Avenshy/mahjong-helper-majsoul-mitmproxy) 的融合和升级。

程序默认配置为启用 `mod`、禁用 `helper` 和 `replace` 。如需自定义，请修改 `config/settings.yaml` 中的 `plugin_enable`。

### `mod` 功能

- [x] 解锁所有角色与皮肤
- [x] 解锁所有装扮
- [x] 解锁所有语音（报菜名）
- [x] 解锁所有称号
- [x] 解锁所有加载 CG
- [x] 解锁所有表情（不推荐开启）
- [x] 强制启用便捷提示
    -   由于雀魂本身代码限制，王座无法正常启用便捷提示，因此，**开启此功能后进入王座对局，左上角会变成 “玉之间”**。请注意，这不是 BUG！
- [x] 支持星标角色
- [x] 自定义名称
- [x] 显示玩家所在服务器
- [x] 显示主播 / Pro 标识
- [ ] 地铁模式
-   TODO……

### `helper` 功能

-   将对局发送到 [mahjong-helper（雀魂小助手）](https://github.com/EndlessCheng/mahjong-helper)

### `replace` 功能

-   替换游戏资源文件，仅支持网页版。
  
## 📄配置文件解释

### `settings.yaml`
这是主程序配置文件，用于存储插件配置和liqi依赖的更新信息。

```yml
# 插件配置，true为开启，false为关闭
plugin_enable:
  mod: true  # mod用于解锁全部角色、皮肤、装扮等
  helper: false  # helper用于将对局发送至雀魂小助手，不使用小助手请勿开启
  replace: false  # replace用于替换雀魂的游戏内容
# liqi用于解析雀魂消息
liqi:
  auto_update: true  # 是否自动更新
  github_token: '' # 仅供自己使用，请勿泄漏给任何人
  liqi_version: 'v0.11.210.w'  # 本地liqi文件版本
  liqi_hash: 'bda101be45d295fb525efd3c20124fa90cb39dd6fd2eca0aeb6e1dd086b6b622'  # 本地liqi文件hash
# 上游代理（可选）：auto=自动读取系统代理 / 填 http://ip:端口 / 留空或direct=直连
proxy:
  upstream: auto
```

### `settings.mod.yaml`
这是mod的配置文件，大多数功能直接在游戏中设定即可，只有小部分无法在游戏中设定的，才在此处修改。

修改完成后需要重新启动MajsoulMax。

只有在启用mod插件后，才会生成该配置文件。

```yml
# 需要自定义的配置主要集中在这里，大多数无需修改，在游戏内设置即可更新
config:
  character: 200001  # 当前看板娘
  characters: {}  # 各角色使用的皮肤
  nickname: '' # 自定义你的名字
  star_chars: [] # 星标角色
  bianjietishi: false # 强制启用便捷提示，用于部分场没有宝牌指示、和牌指示等
  title: 0  # 当前使用的称号
  loading_image: [] # 加载CG
  emoji: false # 不建议开启，用于解锁角色全部emoji，如果你本身角色没有额外表情，在对局中却发送额外表情，这种行为相当于自爆卡车
  views: # 各装扮页的装扮
    0: []
    1: []
    2: []
    3: []
    4: []
    5: []
    6: []
    7: []
    8: []
    9: []
  views_index: 0 # 正在使用的装扮页
  show_server: true # 显示其他玩家所在服务器
  verified: 0 # 标识设置，0为无标识，1为主播标识，2为Pro标识，显示在名字后面
  anti_replace_nickname: true # 禁止将外服玩家设为默认名称，特殊时期必备
  random_character: # 对局随机角色皮肤
    enabled: false
    pool: []
# 资源文件lqc.lqbin的配置                            
resource:
  auto_update: true # 自动更新lqc.lqbin
  lqc_lqbin_version: 'v0.11.104.w' # lqc.lqbin文件版本
# 下面是游戏的资源文件内容，包括需要获得的角色、物品等，不需要修改，除非你要自定义
mod: {}
```
### `settings.helper.yaml`
这是helper的配置文件，若未更改过小助手的地址则无需手动修改。

修改完成后需要重新启动MajsoulMax。

只有在启用helper插件后，才会生成该配置文件。

```yml
config:
  api_url: https://localhost:12121/   # 小助手的地址
```
### `settings.replace.yaml`
这是replace的配置文件，用于存储需要进行替换的游戏文件地址，仅支持网页版，建议在替换前清除浏览器缓存，或在游戏页面使用 `Ctrl+F5` 刷新网页。

修改完成后需要重新启动MajsoulMax。

只有在启用replace插件后，才会生成该配置文件。

```yml
config:
  http: []
  lq: []
```
<details>

<summary>Example</summary>

例如，我需要替换如下3个文件，用于替换柚的足见独白动态皮肤：
- `https://game.maj-soul.com/1/v0.11.155.w/lang/base/extendRes/charactor/you_BL/spine/spine.skel.txt`
- `https://game.maj-soul.com/1/v0.11.155.w/lang/base/extendRes/charactor/you_BL/spine/spine.atlas.txt`
- `https://game.maj-soul.com/1/v0.11.155.w/lang/base/extendRes/charactor/you_BL/spine/you_bl.png`

可以直接在配置文件中填入这三个文件名：

```yml
config:
  http:
  - /spine.skel.txt
  - /spine.atlas.txt
  - /you_bl.png
  lq: []
```

并将这三个用于替换的文件，放入 `MajsoulMax/replace` 文件夹下即可。

但在这里会遇到一个问题，如果需要同时替换其他动态皮肤，这些动态皮肤同样也会使用 `spine.skel.txt` 和 `spine.atlas.txt` 文件，该如何避免冲突呢？

另外，我也希望在玩其他语言服务器时，同样也能将皮肤给替换掉。拿第一个文件 `spine.skel.txt` 来说，我们观察到不同服务器的地址虽然不同，但仍然有相同之处：
- CN: `https://game.maj-soul.com/1/v0.11.155.w/lang/base/extendRes/charactor/you_BL/spine/spine.skel.txt`
- EN: `https://mahjongsoul.game.yo-star.com/v0.11.155.w/en/extendRes/charactor/you_BL/spine/spine.skel.txt`
- JP: `https://game.mahjongsoul.com/v0.11.155.w/jp/extendRes/charactor/you_BL/spine/spine.skel.txt`

根据这些地址可以看出，末尾的 `charactor/you_BL/spine/spine.skel.txt` 这一段是相同的，因此在配置文件中可以据此进行填入：

```yml
config:
  http:
  - /charactor/you_BL/spine/spine.skel.txt
  - /charactor/you_BL/spine/spine.atlas.txt
  - /charactor/you_BL/spine/you_bl.png
  lq: []
```
而文件则需要根据配置文件进行放置，此时文件树如下：
```
MajsoulMax
├─ config
├─ plugin
├─ proto
├─ ...
└─ replace
   └─ charactor
      └─ you_BL
         └─ spine
            ├─ spine.skel.txt
            ├─ spine.atlas.txt
            └─ you_bl.png
```

最终效果如图所示：
<details>
    <summary>🔞NSFW🔞 小孩子不能点哦</summary>


顺便感谢yijyu老师制作的色色l2d动态皮肤，据说也有偿接各种改图，感兴趣的可以去[他的频道（@yijyuqos2）](https://t.me/yijyuqos2)看看

![image.png](https://s2.loli.net/2026/01/15/RZwfEaYVeHMzSId.png)
