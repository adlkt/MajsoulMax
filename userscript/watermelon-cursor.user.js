// ==UserScript==
// @name         🍉 Watermelon Cursor
// @namespace    https://github.com/adlkt/majsoul-wxt-2
// @version      1.1.0
// @description  把鼠标指针换成西瓜切片（来自 majsoul-wxt-2），hotspot (10,5) 对齐真实鼠标点击点。图片已内嵌 base64，零外部依赖、不受网络/CSP 影响。
// @author       wjy
// @match        *://game.maj-soul.com/*
// @match        *://game.mahjongsoul.com/*
// @match        *://game.mahjongchina.com/*
// @match        *://majsoul.henanliuyu.com/*
// @match        *://majsoul.union-game.com/*
// @match        *://mahjongsoul.game.yo-star.com/*
// @match        *://*.hnlygame.com/*
// @match        *://*.catmjstudio.com/*
// @grant        GM_addStyle
// @run-at       document-start
// @license      MIT
// ==/UserScript==

/*
 * hotspot = (10, 5)
 *   - 图片 64×64, PNG
 *   - 凸包分析得到三角形三个角：左上 (10,5) / 右下 (~54,31) / 底部 (~30,58)
 *   - 左上角是西瓜红肉最尖锐的尖端，对应鼠标实际点击位置
 *   - 与浏览器默认箭头光标的 hotspot 位置一致（左上角）
 *
 * 装完脚本后记得【刷新】雀魂页面才生效（Cmd+Shift+R 强刷）。
 * 排查：F12 Console 里搜 "Watermelon Cursor" 日志。
 */
(function () {
    'use strict';
    const DATA_URL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAARmUlEQVR42u1ba3Rc1XX+9jn3zmhm9JYlWZIt+SXJkiwjv0SgARlWiJMmlIRGKuRVaEpC0qSsJCQtbVpZIVl5FEJCCE1DaHCSlRBNCGBeBZLaYxMwMn7JiixskJFlvR+j17zuvefs/rgzkqAUsGPZkHKWlmau5nHX2fvb3/723kfA2+vt9fZ6vdUMCGam1DW3NkoA9P9m86nn315V9O6bFqdXp65bGxvln/TmOenl873eZQ/X126fuXQT919zZfyxK7d8E0AWADCzmG+kPy0DMNNXKlfUtm+5cIjfuZYj5QUON9QxX3cVH/mbphfvaai/OvXeHc0NxlsxLF7Tc0TE7MSrV4+OFcQGhy3H8MiZiUnWLxxzVk9NrPhwdcUv2q5peuyfivPrLmkJOS49vLXC4nU9lgdkPFZefHSDx1w8oxxNQoi0/HwIElqCGaVL5VAgM3FwcPg777n/v74JYIqZxVYitAD6LY0AbmgwxoDpDtu+l4QAMTQrDWd6GkJKoUhKdfwlVdh9zLtlScFNRz97zb4fN1xwFRHpFkC/FcLiNeHa2dNDnQCDqL/e5/1kNkE6AGnlwPT5QUKATENorVj0D6g8Votqq1Z96PKa1Zsy+/raP/VI12AqWwQ7O/kth4AgoLi5WTwYjhw+6ji70wwDDChWCnYsChLCTRUkSHu8hjM6ps2DB9Qmye/74seb2n730Q+2AAg0BYOKW1vlmzFbvD5hhUIyBOiVftPa4PN9SCqHGSRYK5gZAYDcPREzhJSkhRA8OKgyI9Oe5ctLGz52waYPrjM9fetuue1ICOAdzQ3GtlAPv2VIEACx+0b/0xUlR883RfGk42hiCF9hPjz+dLCjQARwSj0IgtaaDcdWWLrUSJQtx6HR8V/f+4vgTbdNJV5IhUVTMKje1CGQ4sKdDQ0SQKTLtn8OaUACGmDY0QggCACDmZPSiQBmCBKkvWmG09evvXv36Hqf8aEbP3vdvsc/fMWXAZipsOBzTJJvKGcv6+lBCOC4snvrM/zX54KlIhArB0bADyEN1/1EAAEEcjHDDGFIYiLSfSdVViziW7lqxWVX1294Xy2je+Nt33uxBcCOhgZjW0+PfrOGgAuD5mZBLS36oZWLH3+/33NZ2LY1MUtPVib8uYuglZr9NgK54cAuIogYTAKsFUvtKCxfbkwtXoKusYmf3HLntn8JAn3MTCAiOsva4Q2z8taWFgEAz0RjPxwnQSYACAFrJgKlHBCldp/avHYNIgAmAYBBhiT2+QzV06MzD+7V9Zlp1976lRv2P3Tlez5NREyAPtthcSo3IgaDQN7dq0uOXGiKZZO2o1lr4cvPhy8zC9qxASEA5uQXE5g4yROpECGQIGhmwEooWbRYYmU5OiZju3/75K4vfb79yLMAwI2Nks4CSZ5KXuadDZslgPiRuH2PlgYEsyYiWNNTYPBs3LtEQGDhhgNp929ElDQMQwhA+H3SGQ8znn1GreHERR/5wJanQ5+46rvVQC4Fg+psVJqnVLikyHCYnZ4LA77r8wmmDQCOIulLg/R4XO+nPJ18BAASBIiUUTD7S0hBbJpCDw6o9JmwKKtc+Y4/v/jCv7rA4x2t/fi17a52aDa2hUJ8zg0QApgbG+V1+9vDW7L8G9ekeariSikwC2YNT3bmrLchksKA4G58Lje4rxGBk4ggAsjrFVopQn+vk2tSbtW62iuvqFldX3S8r/3aRx5ZMEl9yqVrTWenCAIo9opwnd//US9rKCJi24aZlQFhGOAUCmQSASQAKVwwEAApACGSCBFz6VNKkGEKnghrOdini4oLKivesenaLWUlnp8f7GwLdnZa3NoqEQxSKKW7ziIJzusUMRHI2FG5pONikyrCjqNJK+HNy4U/vxBsWXOQJ1cmJwWC632RCg12STNpAADQpgnt8YKkAUMlFAIBiRUVODoe6Xxm156brtn17HYktcMloZBz1hEAAJsbWoxtPXA2BUxfnT/tMmU7CkRCWzY82VkQcCHv/sxzFIm5zacihAgQwjWpIEyB8Lm9z+O+niE8NjQpxiIxXhseUvmZvsLKutqrL68sX422g/tv6OkZd8MCMth5+migPyJ76A1+FP2obOnRGtLpEWYmrci3tATejCxwIg6SYra5OEsAKY/PpkbMXisCDNPAgydH0HywG4YkhGNxPPCeC1GTJjRAEOXV4iSM8L6uozd/4N6HbweguLVVoqlJ02mExemmGM2NjXJfFAMvOs4DXo8JASgSAlZ4AjDlnGmZ5zZP4hUt12TtIF1kSEFQSuOKssXYumY50gDUFuShKDMAEkIws1AH96klfd05V9RVf6fzy3/3+9trqy6ipiZFp9mOO+3+XZIMeZGkodqA7xPpWkMJIk5YkDlZMEwTrBRoluTErBB6GQCFfLlIAkM7Dqpz0nFpYS6uWrUUuYLBSkGAQB5T6FiMRX+fys9OLy3fUHft5atWFLTva2+7vbMzwswCaKFQ6I2h4bQNEASYm5vF+x99ove9eRmXV3mM4rjSipgFg2Dm5QHxOEjKZNzPQX0WHVK6sZ8iRzCU6YHh8wNpXmRnpCFNOdBaux9JFlxEglgaQo2M6MBkGKUryurf9d53XV0paaT+Y9ceCoXAzc3NRigU0gtmAADYjJDc1gO9Lt2kOr///awUsxBCxxPw5OdBCJotiCDcVDh3ZzHrcQhAEyBMAy/EHXyxrQsdUzGEbaAs4IOhFaAxW2+4pTdApknadojHR5y8uvKcqo81Xbn6gnXrf/fbJ/Y98URodEERAADbelyYdU3Eui/Oy/jbUkmBODOTo0h4PTCzs4BE4uWeJ7wsE8y+JgjMjCyD8GTvCB49MYCdfYPon47isqJ8aK0BCJc2OGmMpN6gRTnCKcxm34Zafd4Fl1VdeummazweEdkb0QeaP/MZDr2GivxjdTbvaGgwTgDh5xP2vaZpQjIrMiWs8XHoVIrTAGsGNM9tmuaUIoOhmaEZMKXAjWvKUJqRjhml8ZJlA4YEWCdTKs9+lrQbRsjJgFxeRtrnlyp2Qm3clJXx6Rs2fu/iRd4tLS0tesEQAADRZOc40+CTNf7Ap3KJhRLCJcOsDEifD7CteWSYSoXJR0EQhoQwDZBjw1Ea+QEfVqWZSDNNfOG8SuSSBjt6tsJM1ttgQUCGH1hVCqpbA8pbBMeO03isgw4ebhu6566nfhCN2kMLkQb/V+f4p8OR9mO2s8tnmsSaFRHBGh4FvN7ZOzHY7XYkEaCJAFPiuJYITdug3DyYaV44jsb5Rbm4eWMlVkkNbTkQJMAg8HwwmwaQlw2UlgCFi8FawdKTiFqjzv5nBneMjETbF0oHvGqzpG1m5ocT0oCZ1PV6YgLKtkB+H5g1RLof0u9zewFCgMEgIRCemsLndz6HG9u6cChBMDweOLaCHY1Dafc9boXtqkUkmzHwpwElhaCVy8FpPmjtcIIHqLe3P/HYg50Pu22F19YGZ8QALYBiZvpqb3j7Hyx1wu8xpQY0NMMeG4cOBCC8JnaMTuHBcBQyJwtaawghANtBdWYAyzL8eOpEP24MPYcDIxMwTAMCgEiGPdhlf051nUwDyM8GViwFiksA1rDsSSQwgCOHh47vPzSwAwCCwSAvuAEA8M7NmyWA2OFoZBukAaG1hmnAHhqGIgC+NPSMTeAfn9qPX58Yg/T7wUrDYSDNa+CCnAyELRvHZ2YwI+S8UGeAGazd55Qi0swAUFoMqlgFpPnArBBxTmJkdNB5fPvRVgD9zM0Cr9NjNM5UXb0zKToeGpm8+51+/5cqDOmNAkwJi5zwBDwFuUhP8yLdMHHLcx3IrytHw+JsOFpDOwqfqVkGyRqLCwrwzvws6GgUguepe4JLpGCwzwOU5IOqK4DiEjArxKxxdowBOtDWe/z++zt+6QKlBWeFA5JhoLmxUT46Ee/psJxHPB4PCWZFhoQ9MAR4ffCDkdAaQ7EYdo+EAcMAawYxI0CML6yvwIeX5ALRqNtKm6s8kiU1XOgX5QOVK4HKCrBhQOsER5weDAyedLYHO1oBvPBGvH9G0uCrN0toZH16+l/7WUELSUjEITOzsDQnAyfHJ5GbmYkv1FUg07HdXiEzmAHlKGjHgcAr6jpO6gZDAgW5wJpy0Kb1QH4hmG1E48OY1p148uHOfbfd+tQ/MPM00SXJhsNrL+NMGqApSYZEFPqL3Oz2d3mNtZbjKGiW1vAwAuUr8W/1VW5qjMfASkPMG6bIeYUi8zzpSwySBM7JAFaVAuetAYpLoNmB7UR4Rh+jnu6+wW3/0XY3gN6tW7e+Ie+fcQMAwM7NJAE4B2eid13ky/6+hMNsGlDDo3DKlrmDxqlpd7QuhasOU8SWAn2K7OZ1izgrHagoA62rAVasAAsBVjGejL+I6cTJ6ft+dnjn/kMD9yYdwAvdD/g/1yUhKAC4+/jIL/9g63CaaRoaYLYsOMPDEIH0ZHyTu/F5wmg238EtnzmJfuRkAuVloPNqgMoqwOsDawvT8UEk5HHaEzo+eNe/P30HgCl3uIRzZwAkO8ddwNjhWPxXhmGAHK1ISFj9A2DTA0rNElPeTz1PxXuqcpQCyMlyPb92NVC9GkjPgFYJxO0JntZH6Pix/sEf3Lr77riD3ydFzymN1owFMACagkEAwKNj4R/+mS/tkyVCyAQzEInADk/A6/dDT066vQK8wl/khgCbEsjNBlYucdNdbQ2QlQutLNhqRo8nDonpmaHw97/x1CN79w3ckYS+PlstsTdUH7SORA8dSVghn5RgzQoQsPoGwD7fbDk7hwDMTZS8yVRXswI4rxpYWwtk54GVDcVRjMUPiZjqj911+zNP33d/x7cARE4V+guSBl/tZMkyjxFZnxFokspmllJwNAKjsMCVwZY1NyAhzFV3ZSVA1QpQbRWoqgpIz4TWFiuOon9in+3gZOevfnKg+xtf2/l1APuT+9ALPRs89foATN/oG3+4I271BAxDaq012w6s/gFQRoY7MhfJAifNBBbngWrKQetrQPXrgaoawJcOrRPQiNBIbD9pT1+i9T/3DzTf9MR3AexsbIQEoM7GcPTU64PkMPVwLH4Pp+oDacIaGIICgXxet4OclwVUloE2rgHOXwdsWg+UroAmyUpFtaXHuXd0z7CD/hfu++mhozff/OSvFfCbxkbIYPD0N7+wITBvmGrFVPeGrMD1BQSPBYDjcZI5mTBWlQJ5mUD1SlBNBbCmCli5ChzIhFY2S9OmqNNP49YBgpjc862v/Pbkrd/esT2e4DubmyHuvPOPP0xhLKQBUvUBBYMnuuLxh9Zk+JpiluVwht+IxqbhWVcNZKeDihaDCwtB/gywVoCOQXri1D/aNRxT3VFHJcL//PcP0W8eOLILwPeamyFaWs7hbPBUVisgmwD9icJAQ0t52Y6Al7SVmyGsXB+yP/JxpG96B3TyEAUri5kTiNhD8dFwV7dJY//d9mwfff3rj689eGj4ZwB+nAxbxhkajhoLbYB59cGuq+p87RetLlg7U5ClJkpz5aQZ4RpPOmCFSTsWx51xiugeTER6pkkldt15+56cXwX3V/T1R74J4P5kyJ7RUyMLbgAA2Lp1swTg7Ibzo+pL1t8xEiCeNg2emTlBS6ZehGkwT8a7Kar7oVWk4/De/vbvfntnzaGDJ52Era8HcGAhNo+zeJCZAHBmdWbuPd+64fmlxb5F45Ep9PUOPl9SsGS6/uLijSPh3sjxzrEn77hld+TZtpfqYjHrqZw8ddOJEwgv1ObPGgLcYU6rJGoa7zp04mfpmSXXHTt6fO9o79jvTzz/0oyD86ztv3l2/OH7OwpjCTsgDdw6HVE/mY7Mpmr1ZjglhjNwIItXr15S0/SX1Z8zjcSx7pcmfe0dQyv7+6ZLASyyHec5245/bXIS3Wea7M41AtzGlkuGnXv2ek8oR6/ven6k3DSMHJ/feGFmJvGvo6PxB+bpk3N+jhgLdSgrP9//7uKiQG/xYv/uoiL/dQDS5yHyT/MfsF6xPLm58jIA2WdLlb7ZUUF4e7293l7nYv0Pv0BdP6+M+YAAAAAASUVORK5CYII=';
    const hot = '10 5';
    console.log('[Watermelon Cursor] loaded @', location.host);
    GM_addStyle(`
        html, body {
            cursor: url("${DATA_URL}") ${hot}, auto !important;
        }
        *, *::before, *::after {
            cursor: url("${DATA_URL}") ${hot}, auto !important;
        }
        a, button, [role="button"], input[type="submit"], input[type="button"] {
            cursor: url("${DATA_URL}") ${hot}, pointer !important;
        }
    `);
})();
