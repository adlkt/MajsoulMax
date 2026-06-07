# 已知问题

## 传记红点（简等新角色）

### 现象
部分后期角色（如简 20000106）的传记 tab 出现无法消除的红点。

### 根因
雀魂的传记系统有两个版本：

| 版本 | 数据来源 | 覆盖 |
|------|---------|------|
| 旧系统 | `lqc.lqbin` → `spot_rewards` / `spot_spot` | 前 63 个角色 |
| 新系统 | 客户端本地 AssetBundle | 后期角色（如简） |

`lqc.lqbin` 由 `game.maj-soul.com` 下发，mod 能从中提取旧系统的传记 ID 并注入为"已完成"。但新系统的传记数据不在 `lqc.lqbin` 中，而是存储在客户端资源文件里，mod 无法获取对应的 `story_id`，因此无法标记为已完成。

客户端检测到"有传记数据但服务端返回进度为空"→ 亮红点。

### 尝试过的方案（均失败）

1. **注入 `activity_data.spot_data`**：从 `SpotRewards` 反推 `unique_id` 并注入完成状态，但简的传记不在旧系统中，无效。
2. **注入 `activity_data.story_data`**：同上，缺少简的 `story_id`。
3. **移除 `is_upgraded=True`**：让传记 tab 不可访问来消除红点，无效（红点可能走其他触发路径）。
4. **选择性注入角色**：只注入有传记数据的角色（跳过简），但用户仍需使用该角色。

### 可能的解决方向（未实现）

- 逆向客户端 AssetBundle 提取新传记系统的 `story_id` 映射
- 等待 `lqc.lqbin` 更新包含新角色传记数据
- 从有该角色的真实账号抓取 `fetchInfo` 响应

---

## 皮肤特效缺失

部分角色的动态皮肤/Spine 动画特效未生效。

### 推测根因
皮肤特效可能绑定了好感物品（category 2 的物品如饼干/礼物），mod 只注入了 category 5（装饰品）和 category 8（加载 CG）的背包物品，缺少好感类物品。

### 待验证
需要抓取 `fetchBagInfo` 对比真实账号和 mod 注入后的背包差异。

---

## lqc.lqbin 数据覆盖不全

`lqc.lqbin` 包含 200+ 张数据表，但 mod 只使用其中少数：

| 表 | 用途 | 状态 |
|----|------|------|
| `item_definition_character` | 角色列表 | ✅ 完整 |
| `item_definition_skin` | 皮肤列表 | ✅ 完整 |
| `item_definition_item` | 物品列表 | ⚠️ 只取 category 5+8 |
| `spot_rewards` | 旧传记结局 | ✅ 但只覆盖 63/122 角色 |
| `spot_spot` | 旧传记正文 | ❌ 未使用（126 条） |

新角色（20000100+）的传记、好感度等数据存储在客户端本地的 Unity AssetBundle 中，不在 `lqc.lqbin` 里。
