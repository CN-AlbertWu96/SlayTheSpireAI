# ============================================================================
# gamestatetooutput.py - 游戏状态解析与 AI 决策核心模块
# ============================================================================
# 这个文件是整个 AI 机器人的"大脑"，负责：
# 1. 加载游戏数据字典（卡牌、遗物、药水、能力效果描述）
# 2. 调用大模型 API（支持 Claude / OpenAI 兼容接口）
# 3. 将游戏状态 JSON 转换为自然语言 Prompt，发送给大模型
# 4. 解析大模型返回的文本，提取可执行的游戏命令
#
# 整体流程：
#   游戏状态 JSON → 构建 Prompt → 调用 LLM → 解析响应 → 返回命令列表
# ============================================================================

import json, anthropic, re, os, sys, openai, time

# ============================================================================
# 第一部分：加载游戏数据字典
# ============================================================================
# 这些 JSON 文件包含了杀戮尖塔中所有卡牌、遗物、药水、能力的效果描述
# 格式：{"卡牌名": "效果描述"}
# 这些描述会被嵌入到 Prompt 中，让大模型了解每张牌的作用
dir_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data")

with open(os.path.join(dir_path, "cardlist.json"), "r", encoding="utf-8") as f:
    cardlist = json.load(f)    # 所有卡牌效果，如 {"Strike": "Deal 6 damage."}

with open(os.path.join(dir_path, "powerlist.json"), "r", encoding="utf-8") as f:
    powerlist = json.load(f)   # 所有能力效果，如 {"Vulnerable": "Takes 50% more damage from attacks."}

with open(os.path.join(dir_path, "reliclist.json"), "r", encoding="utf-8") as f:
    reliclist = json.load(f)   # 所有遗物效果，如 {"Burning Blood": "At the end of combat, heal 6 HP."}

with open(os.path.join(dir_path, "potionlist.json"), "r", encoding="utf-8") as f:
    potionlist = json.load(f)  # 所有药水效果，如 {"Fire Potion": "Deal 20 damage."}

# 将所有字典的 key 转为小写，方便后续不区分大小写地查找
cardlist = {k.lower(): v for k, v in cardlist.items()}
powerlist = {k.lower(): v for k, v in powerlist.items()}
reliclist = {k.lower(): v for k, v in reliclist.items()}
potionlist = {k.lower(): v for k, v in potionlist.items()}

# ============================================================================
# 第二部分：初始化大模型 API 客户端
# ============================================================================
# 支持两种 API：
# 1. Claude (Anthropic) - 需要 CLAUDE_API_KEY
# 2. OpenAI 兼容接口 - 用于腾讯云等第三方模型（如 hunyuan-turbos）

# Claude 客户端（仅在需要时初始化，延迟加载模式）
claude_client = None

def get_claude_client():
    """延迟初始化 Claude 客户端，只在第一次调用且配置了 API Key 时创建"""
    global claude_client
    if claude_client is None and os.getenv("CLAUDE_API_KEY"):
        try:
            claude_client = anthropic.Client(api_key=os.getenv("CLAUDE_API_KEY"))
        except Exception as e:
            print(f"Warning: Failed to initialize Claude client: {e}")
    return claude_client

# OpenAI 兼容接口配置（腾讯云 hunyuan 等模型使用此接口）
# 从 .env 环境变量读取配置
TENCENT_API_KEY = os.getenv("TENCENT_API_KEY")
TENCENT_API_URL = os.getenv("TENCENT_API_URL", "https://api.lkeap.cloud.tencent.com/coding/v3")

if not TENCENT_API_KEY:
    raise ValueError("TENCENT_API_KEY environment variable not set. Please set it before running the bot.")

# 创建 OpenAI 兼容客户端
# 关键：通过设置 base_url 指向腾讯云 API，可以复用 OpenAI SDK 调用任何兼容接口
openai_client = openai.Client(
    api_key=TENCENT_API_KEY,
    base_url=TENCENT_API_URL
)

# 使用的模型名称，如 "hunyuan-turbos", "glm-5" 等
model = os.getenv("TENCENT_MODEL")
print(f"[DEBUG] Loaded model from env: {model}")

"""
"claude-3-5-sonnet-20240620"
"""

# ============================================================================
# 第三部分：大模型 API 调用函数
# ============================================================================

def GPT(messages, model=model, debug_print=None):
    """
    统一的大模型调用接口
    
    根据 model 名称自动选择 Claude 或 OpenAI 兼容接口。
    
    Args:
        messages: 对话历史列表，格式：[{"role": "user", "content": "..."}, ...]
        model: 模型名称，包含 "claude" 则用 Claude API，否则用 OpenAI 兼容接口
        debug_print: GUI 日志函数（可选），传入后日志会显示在 GUI 右侧面板
    
    Returns:
        str: 模型生成的回复文本
    """
    def log(msg):
        """统一日志输出 - 优先输出到 GUI，否则输出到 stdout"""
        if debug_print:
            debug_print(msg)
        else:
            print(msg)
    
    # ---- Claude API 路径 ----
    if "claude" in model:
        client = get_claude_client()
        if client is None:
            raise ValueError("Claude API key not configured. Please set CLAUDE_API_KEY environment variable.")
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0,     # temperature=0 让输出更确定性，减少随机性
            messages=messages
        )
        
        return response.content[0].text
    
    # ---- OpenAI 兼容接口路径（腾讯云 hunyuan 等）----
    else:
        try:
            log(f"[API] Calling OpenAI-compatible API with model: {model}")
            response = openai_client.chat.completions.create(
                model=model,
                max_tokens=2000,   # 最大输出 token 数
                temperature=0,     # 确定性输出
                messages=messages,
                timeout=60.0       # 60 秒超时，防止无限等待
            )
            
            # 检查响应结构是否正常
            if not response.choices or len(response.choices) == 0:
                log(f"[API] No choices in response: {response}")
                return ""
            
            content = response.choices[0].message.content
            log(f"[API] Response content length: {len(content) if content else 0}")
            
            return content
        except Exception as e:
            log(f"[API] Exception in GPT call: {type(e).__name__}: {e}")
            raise e

# ============================================================================
# 第四部分：核心函数 - 游戏状态 → AI 决策命令
# ============================================================================
# 这是整个模块最重要的函数，负责：
# 1. 解析游戏状态 JSON
# 2. 根据不同的游戏界面类型（战斗、地图、商店、事件等）构建 Prompt
# 3. 调用大模型 API 获取决策
# 4. 解析大模型回复，提取可执行命令
# 5. 对命令进行后处理（排序、补全、验证等）

def gamestate_to_output(input_json, print, debug_print, messages=[]):
    """
    将游戏状态转换为 AI 决策命令
    
    Args:
        input_json: Communication Mod 发送的游戏状态 JSON 字符串
        print: INFO 日志函数（显示在 GUI 左侧面板）
        debug_print: DEBUG 日志函数（显示在 GUI 右侧面板）
        messages: 对话历史（可变默认参数，跨调用保持上下文）
                  注意：这是一个常见的 Python "陷阱" - 可变默认参数在函数定义时只创建一次
                  但在这里是故意利用这个特性来保持对话上下文
    
    Returns:
        tuple: (commands, is_combat)
            - commands: 命令字符串列表，如 ["play Strike 0", "end"]
            - is_combat: 布尔值，是否在战斗中
    """
    start_time = time.time()
    debug_print(f"[PERF] Starting gamestate_to_output")

    # ====================================================================
    # 步骤 1：解析 JSON 并提取游戏状态
    # ====================================================================
    state = json.loads(input_json.replace(",\n        ...", ""))
    debug_print(f"[PERF] JSON parsed in {time.time() - start_time:.2f}s")

    # 检查是否在游戏中
    if "in_game" in state:
        if not state["in_game"]:
            debug_print("Not in game")
            return [], False

    # keep_messages 控制是否保留对话历史
    # 大多数情况清空历史（每次重新开始），只有某些连续交互保留（如手牌选择）
    keep_messages = False

    # 处理嵌套的 JSON 结构：有些状态直接是 game_state 的内容，有些包了一层
    if "relics" not in state:
        state = state["game_state"]

    # 商店房间只有一个选项时，自动选择
    if "choice_list" in state and len(state["choice_list"]) == 1 and state["screen_type"] == "SHOP_ROOM":
        return ["choose 0"], False

    # ====================================================================
    # 步骤 2：构建基础 Prompt - 通用游戏信息
    # ====================================================================
    # 地图符号 → 可读名称的映射
    map_dict = {
        "M": "Normal Enemy",    # 普通敌人
        "E": "Elite Enemy",     # 精英敌人
        "$": "Shop",            # 商店
        "?": "?",               # 未知事件
        "R": "Rest Site",       # 休息点
        "T": "Treasure",        # 宝箱
    }

    # 构建药水信息字符串
    potions_str = ""
    for potion in state["potions"]:
        # 支持中英文药水栏名称（游戏语言不同）
        if potion["name"] not in ["Potion Slot", "药水栏"]:
            if potion['name'].lower() not in potionlist:
                debug_print("Unknown potion:", potion['name'])
            potions_str += f"{potion['name']}: {potionlist[potion['name'].lower()]}\n"
        else:
            potions_str += "Empty Slot\n"

    # 构建遗物信息字符串
    relics_str = ""
    for relic in state["relics"]:
        if relic['name'].lower() not in reliclist:
            debug_print("Unknown relic:", relic['name'])
        if relic["counter"] >= -1:
            # 某些遗物有计数器（如 Nunchaku 每打 10 张牌获得 1 能量）
            counter = f" (Counter: {relic['counter']})" if relic["counter"] > -1 else ""
            relics_str += f"{relic['name']}{counter}: {reliclist[relic['name'].lower()]}\n"

    # 构建基础 Prompt：角色信息 + HP + 金币 + 楼层 + 药水 + 遗物
    prompt = f"""You are currently playing Slay the Spire as the {state["class"][0] + state["class"].lower()[1:]}. Cards have their energy cost in parenthesis next to them. Only use curly brackets when you perform an action.\nGame state:
Current HP: {state["current_hp"]}
Max HP: {state["max_hp"]}
Gold: {state["gold"]}
Floor: {state["floor"]}
Act: {state["act"]}

Potions:
{potions_str}
Relics:
{relics_str}
"""
    # 非战斗状态时显示完整牌组
    cards_in_deck = []
    if "combat_state" not in state:
        prompt += "Deck:\n"
        for card in state["deck"]:
            if card["name"].lower() not in cardlist:
                debug_print("Unknown card:", card["name"])
            else:
                # 能量消耗显示：-1 → X（可变费用），-2 → Unplayable（不可打出）
                prompt += f"{card['name']} ({'X' if card['cost'] == -1 else (card['cost'] if card['cost'] != -2 else 'Unplayable')} Energy)\n"
                cards_in_deck.append(card["name"].lower())
    prompt += "\n\n\n\n"

    # ====================================================================
    # 步骤 3：根据游戏界面类型，构建特定的 Prompt
    # ====================================================================
    # 游戏有多种界面：地图选择、事件、战斗、商店、休息点、卡牌奖励等
    # 每种界面需要不同的 Prompt 格式和操作指令
    
    combat_hand = []          # 当前手牌列表（战斗中使用）
    shop_things = []          # 商店可购买物品列表
    requires_confirm = False  # 是否需要追加 "confirm" 命令
    is_combat_reward = False  # 是否在战斗奖励界面
    is_combat = False         # 是否在战斗中
    is_shop = False           # 是否在商店

    # ---- 场景 A：地图选择（选择下一个节点）----
    if "next_nodes" in state["screen_state"]:
        # 只有一个选项时自动选择
        if "choice_list" in state and len(state["choice_list"]) == 1:
            return ["choose 0"], False
        choices = {}
        i = 0
        for node in state["screen_state"]["next_nodes"]:
            if node["symbol"] in map_dict:
                choices[map_dict[node["symbol"]]] = i
            else:
                debug_print("Unknown symbol:", node["symbol"])
            i += 1
        if len(choices) == 1:
            return ["choose 0"], False
        
        prompt += f"Map: Choose next location.\nOptions: {', '.join([f'{i}: {k}' for i, k in enumerate(choices.keys())])}\nAction: {{choose index}}"""
    
    # ---- 场景 B：事件 / 休息已完成 ----
    elif state["screen_type"] == "EVENT" or state["screen_type"] == "REST":
        if state["screen_type"] == "REST":
            if state["screen_state"]["has_rested"]:
                return ["proceed"], False
            
        if "choice_list" in state and len(state["choice_list"]) == 1:
            return ["choose 0"], False
        
        choices = []
        if state["screen_type"] == "REST":
            for option in state.get("choice_list", []):
                choices.append(option)
        else:
            for option in state["screen_state"]["options"]:
                choices.append(option["text"])
        
        event_text = f" {state['screen_state']['body_text']}" if 'body_text' in state['screen_state'] and state['screen_state']['body_text'] else ""
        prompt += f"Event: {state['screen_state']['event_name'] if state['screen_type'] == 'EVENT' else 'Rest'}\nText: {event_text}\nOptions: {', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}}"

    # ---- 场景 C：手牌选择（如 Headbutt 选择弃牌堆的牌）----
    elif state["screen_type"] == "HAND_SELECT":
        requires_confirm = True   # 选择完需要确认
        keep_messages = True      # 保持对话上下文（可能是连续交互）
        choices = state.get("choice_list", [])
        prompt = f"Select cards.\nOptions: {', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}}"

    # ---- 场景 D：战斗界面（最复杂的场景）----
    elif "combat_state" in state:
        is_combat = True
        # 战斗中弹出卡牌奖励（战斗途中的特殊事件）
        if state["screen_type"] == "CARD_REWARD":
            requires_confirm = True
            keep_messages = True
            choices = state.get("choice_list", [])
            prompt = f"Card Reward (choose one):\n{', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}} or {{skip}}"
        else:
            # ---- 常规战斗回合 ----
            unique_cards = set()

            def pile_to_str(pile, fill_combat_hand=False):
                """
                将卡牌堆转换为可读字符串
                
                Args:
                    pile: 卡牌列表（来自游戏 JSON）
                    fill_combat_hand: 是否同时填充 combat_hand 列表（只对手牌使用）
                """
                pile_str = ""
                for card in pile:
                    if fill_combat_hand:
                        combat_hand.append(card["name"])  # 记录手牌，后续命令解析用
                        unique_cards.add(card["name"].lower())
                    pile_str += f"{card['name']} ({'X' if card['cost'] == -1 else (card['cost'] if card['cost'] != -2 else 'Unplayable')}) "
                if pile_str == "":
                    pile_str = "Empty"
                return pile_str.strip()
            
            # 转换三个牌堆为字符串，同时填充 combat_hand
            draw_pile = pile_to_str(state["combat_state"]["draw_pile"])
            discard_pile = pile_to_str(state["combat_state"]["discard_pile"])
            hand = pile_to_str(state["combat_state"]["hand"], fill_combat_hand=True)

            # 只发送手牌中卡牌的效果描述（减少 token 消耗）
            card_descriptions = ""
            for card in combat_hand:
                card_lower = card.lower()
                if card_lower in cardlist:
                    card_descriptions += f"{card}: {cardlist[card_lower]}\n"

            # 构建敌人信息
            monsters = ""
            for i, monster in enumerate(state["combat_state"]["monsters"]):
                if not monster["is_gone"]:  # 跳过已死亡的敌人
                    # 解析敌人意图（下一步行动）
                    if monster["intent"] == "ATTACK" or monster["move_base_damage"] > 0:
                        hits_str = f"x{monster['move_hits']}" if monster['move_hits'] > 1 else ''
                        intent = f"Attack {monster['move_adjusted_damage']}{hits_str}"
                    elif monster["intent"] == "DEBUG":
                        intent = "Buff"
                        debug_print("DEBUG INTENT", i)
                    elif monster["intent"] == "UNKNOWN":
                        intent = "Unknown"
                    else:
                        intent = monster["intent"].lower().capitalize()

                    # 构建敌人能力列表
                    for power in monster['powers']:
                        if power['name'].lower() not in powerlist:
                            debug_print("Unknown power:", power['name'])
                            monster['powers'].remove(power)

                    powers_str = ", ".join([f"{power['amount']} {power['name']}" for power in monster['powers']]) if monster['powers'] else "None"
                    monsters += f"[{i}] {monster['name']}: {monster['current_hp']}/{monster['max_hp']}HP, {monster['block']} block, Intent: {intent}, Powers: {powers_str}\n"

            # 构建玩家能力信息
            player_powers = ""
            for power in state["combat_state"]["player"]["powers"]:
                if power['name'].lower() not in powerlist:
                    debug_print("Unknown power:", power['name'])
                else:
                    player_powers += f"{power['amount']} {power['name']}, "
            if player_powers:
                player_powers = f"\nYour Powers: {player_powers.strip(', ')}"

            # 计算可用的目标索引（只包含存活的敌人）
            available_targets = [i for i, m in enumerate(state["combat_state"]["monsters"]) if not m["is_gone"]]
            targets_str = ", ".join(map(str, available_targets))
            
            prompt += f"""Combat State:
Energy: {state["combat_state"]["player"]["energy"]} (IMPORTANT: Total cost of cards played cannot exceed this!)
Hand: {hand}
Draw Pile: {draw_pile}
Discard Pile: {discard_pile}{player_powers}

Enemies:
{monsters}
Card Effects:
{card_descriptions}
Available Targets: {targets_str} (CRITICAL: Only use these indices!)

Actions:
- {{play CardName}} for block/defense cards (no target needed)
- {{play CardName target_number}} for attack cards (use Available Targets above)
- {{end}} to end your turn

Examples:
{{play Defend}} - correct
{{play Strike {available_targets[0]}}} - correct (Strike targets enemy {available_targets[0]})

Rules: 
1. Only play cards in hand
2. TOTAL ENERGY COST must not exceed {state["combat_state"]["player"]["energy"]}
3. Each card instance can only be played ONCE per turn
4. If you have multiple cards with the same name, count them in your Hand list above
5. Prioritize 0-cost cards when possible
6. ALWAYS end your turn with {{end}} command after playing all desired cards
7. Use {{}} only for actions
8. ONLY use target numbers from Available Targets list"""

    # ---- 场景 E：商店界面 ----
    elif state["screen_type"] == "SHOP_SCREEN":
        is_shop = True
        cards = ""
        relics = ""
        potions = ""
        # 遍历商店中的卡牌、遗物、药水，构建商品列表
        for card in state["screen_state"]["cards"]:
            if card["name"].lower() not in cardlist:
                debug_print("Unknown card:", card["name"])
            cards += f"""{card["name"]} ({card["price"]} gold) (costs {card["cost"]} energy in combat): {cardlist[card["name"].lower()]}\n"""
            shop_things.append(card["name"].lower())
        for relic in state["screen_state"]["relics"]:
            if relic["name"].lower() not in reliclist:
                debug_print("Unknown relic:", relic["name"])
            relics += f"""{relic["name"]} ({relic["price"]} gold) (costs {card["cost"]} energy in combat): {reliclist[relic["name"].lower()]}\n"""
            shop_things.append(relic["name"].lower())
        for potion in state["screen_state"]["potions"]:
            if potion["name"].lower() not in potionlist:
                debug_print("Unknown potion:", potion["name"])
            potions += f"""{potion["name"]} ({potion["price"]} gold) (costs {card["cost"]} energy in combat): {potionlist[potion["name"].lower()]}\n"""
            shop_things.append(potion["name"].lower())
        prompt += f"""Shop (Gold: {state['gold']})
Cards: {cards}Relics: {relics}Potions: {potions}"""
        if state["screen_state"]["purge_available"]:
            prompt += f"Card Removal: {state['screen_state']['purge_cost']} gold\n"
        prompt += "Actions: {{buy itemname}} {{potion discard slot}}. Check gold before buying."
    
    # ---- 场景 F：休息点（休息/铁匠升级）----
    elif state["screen_type"] == "REST_SITE":
        choices = {}
        for option in state["screen_state"]["options"]:
            choices[option["label"]] = option["choice_index"]
        
        if len(choices) == 1:
            return ["choose 0"], False

        prompt += f"Rest Site. HP: {state['current_hp']}/{state['max_hp']}\nOptions: {', '.join([f'{i}: {k}' for i, k in enumerate(choices.keys())])}\nAction: {{choose index}}"
            
    # ---- 场景 G：卡牌奖励（战斗后选择卡牌）----
    elif state["screen_type"] == "CARD_REWARD":
        cards = ""
        for card in state["screen_state"]["cards"]:
            if card["name"].lower() not in cardlist:
                debug_print("Unknown card:", card["name"])
            cards += f"{card['name']} ({'X' if card['cost'] == -1 else (card['cost'] if card['cost'] != -2 else 'Unplayable')} Energy): {cardlist[card['name'].lower()]}\n"
        prompt += f"Card Reward:\n{cards}Action: {{choose index}} or {{skip}}"
    
    # ---- 场景 H：战斗奖励（金币、遗物、药水等）----
    elif state["screen_type"] == "COMBAT_REWARD":
        is_combat_reward = True
        if len(state["screen_state"]["rewards"]) == 0:
            return ["proceed"], False
        reward_list = []
        for reward in state['screen_state']['rewards']:
            if reward["reward_type"] == "CARD":
                reward_list.append("Card Reward")
            elif reward["reward_type"] == "RELIC":
                if reward["relic"]["name"].lower() not in reliclist:
                    debug_print("Unknown relic:", reward["relic"]["name"])
                else:
                    reward_list.append("Relic: " + reward["relic"]["name"] + " (" + reliclist[reward["relic"]["name"].lower()] + ")")
            elif reward["reward_type"] == "POTION":
                if reward["potion"]["name"].lower() not in potionlist:
                    debug_print("Unknown potion:", reward["potion"]["name"])
                else:
                    reward_list.append("Potion: " + reward["potion"]["name"] + " (" + potionlist[reward["potion"]["name"].lower()] + ")")
            elif reward["reward_type"] == "GOLD":
                reward_list.append(str(reward["gold"]) + " Gold")
            elif reward["reward_type"] == "STOLEN_GOLD":
                reward_list.append(str(reward["gold"]) + " Gold (Stolen)")
            else:
                debug_print("Unknown reward type:", reward["reward_type"])
                reward_list.append(reward["reward_type"])

        rewards = "- " + "\n- ".join(reward_list)
        prompt += f"Combat Rewards (all free, choose multiple):\n{rewards}\nAction: {{choose index}} {{potion discard slot}}"
        
    # ---- 场景 I：网格选择（如 Headbutt 选择弃牌堆的牌放到抽牌堆顶）----
    elif state["screen_type"] == "GRID":
        requires_confirm = True
        keep_messages = True
        choices = state.get("choice_list", [])
        debug_print(f"[GRID] Screen detected, choices: {choices}")
        
        prompt = f"Grid selection:\n{', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}}"
        # 如果是升级选择界面，显示升级后的效果
        if state["screen_state"]["for_upgrade"]:
            prompt += "\nUpgraded versions:\n"
            for card in state["deck"]:
                name = card['name']
                if not name.endswith("+"):
                    name += "+"
                if card["name"].lower() not in cardlist:
                    debug_print("Unknown card:", card["name"])
                else:
                    prompt += f"{name} ({card['cost']}): {cardlist[name.lower()]}\n"
    
    # ---- 场景 J：宝箱 ----
    elif state["screen_type"] == "CHEST":
        if not state["screen_state"]["chest_open"]:
            return ["choose 0"], False  # 自动打开宝箱
    
    # ---- 场景 K：Boss 遗物奖励 ----
    elif state["screen_type"] == "BOSS_REWARD":
        relics = ""
        for relic in state["screen_state"]["relics"]:
            if relic["name"].lower() not in reliclist:
                debug_print("Unknown relic:", relic["name"])
            else:
                relics += f"{relic['name']}: {reliclist[relic['name'].lower()]}\n"
        prompt += f"Boss Relic (choose one):\n{relics}Action: {{choose index}} or {{skip}}"
    
    # ---- 未知界面类型 ----
    else:
        debug_print("Unknown screen type:", state["screen_type"])
        return [], False

    # ====================================================================
    # 步骤 4：管理对话历史 + 调用大模型 API
    # ====================================================================
    # 大多数场景清空对话历史（每次独立决策）
    # 少数连续交互场景保留历史（如 HAND_SELECT、GRID）
    if not keep_messages:
        while len(messages) > 0:
            messages.pop()

    debug_print(f"[PERF] Prompt generated in {time.time() - start_time:.2f}s, length={len(prompt)} chars")
    print("Generating with prompt:\n" + prompt + "\n\n\n")
    messages.append({"role": "user", "content": prompt})

    # 调用大模型 API
    api_start = time.time()
    debug_print(f"[PERF] Starting API call with model: {model}")
    try:
        response = GPT(messages, debug_print=debug_print)
        api_elapsed = time.time() - api_start
        debug_print(f"[PERF] API call completed in {api_elapsed:.2f}s")
        
        # 检查空响应并重试一次
        if not response or response.strip() == "":
            debug_print("[PERF] API returned empty response")
            debug_print(f"[PERF] Response type: {type(response)}, value: '{response}'")
            
            debug_print("[PERF] Retrying API call...")
            try:
                response = GPT(messages, debug_print=debug_print)
                api_elapsed = time.time() - api_start
                debug_print(f"[PERF] Retry API call completed in {api_elapsed:.2f}s")
                
                if not response or response.strip() == "":
                    debug_print("[PERF] Retry also returned empty response, giving up")
                    return [], False
            except Exception as retry_e:
                debug_print(f"[PERF] Retry failed: {retry_e}")
                return [], False
    except Exception as e:
        api_elapsed = time.time() - api_start
        debug_print(f"[PERF] API call failed after {api_elapsed:.2f}s: {e}")
        debug_print(f"[PERF] Exception type: {type(e).__name__}")
        return [], False
    
    if not response or response.strip() == "":
        debug_print("API returned empty response after retry")
        return [], False
    
    # 将 AI 回复加入对话历史
    messages.append({"role": "assistant", "content": response})
    print("Response:\n" + response + "\n\n\n")

    # ====================================================================
    # 步骤 5：解析大模型回复，提取可执行命令
    # ====================================================================
    # AI 回复格式示例：
    #   "I'll play Strike to deal damage. {play Strike 0} Then defend. {play Defend} {end}"
    # 用正则提取所有 {xxx} 中的内容
    matches = re.findall(r"\{(.*?)\}", response)
    commands = []
    
    for match in matches:
        command = None
        action = match.split()[0]          # 动作类型：play, choose, end, buy, potion, skip
        arg = " ".join(match.split()[1:])  # 动作参数
        
        # ---- 处理 "play" 命令（出牌）----
        if action == "play":
            target = ""
            # 移除 "target" 关键字（AI 有时会写 "play Strike target 0"）
            arg_parts = arg.split()
            if "target" in arg_parts:
                arg_parts.remove("target")
                arg = " ".join(arg_parts)
            
            # 提取目标索引（最后一个数字）
            if arg.split()[-1].isdigit():
                target = int(arg.split()[-1])
                arg = " ".join(arg.split()[:-1])
            else:
                # 没有指定目标，默认选择第一个存活的敌人
                i = 0
                for m in state["combat_state"]["monsters"]:
                    if not m["is_gone"]:
                        target = i
                        break
                    i += 1
            
            # 清理卡牌名称：移除括号部分（如 "Defend (1)" -> "Defend"）
            # AI 可能看到 "Defend (1)" 格式，但 combat_hand 只有 "Defend"
            arg_cleaned = re.sub(r'\s*\([^)]*\)', '', arg).strip()
            
            # 进一步清理：移除末尾的数字（如 "Headbutt 1" -> "Headbutt"）
            # 这处理模型错误地在卡牌名后添加数字的情况
            if arg_cleaned and arg_cleaned.split()[-1].isdigit():
                arg_cleaned = ' '.join(arg_cleaned.split()[:-1])
            
            if arg_cleaned in combat_hand:
                arg = arg_cleaned
            elif arg not in combat_hand:
                debug_print("Could not find card in hand:", arg, "Hand:", combat_hand)

            command = f"play {arg} {target}"
            commands.append(command)
            #combat_hand.remove(arg)  # 注释掉：不在这里移除，因为可能有重复牌名

        # ---- 处理 "choose" 命令（选择选项）----
        elif action == "choose":
            commands.append("choose " + arg)
        
        # ---- 处理 "end" 命令（结束回合）----
        elif action == "end":
            commands.append(action)
        
        # ---- 处理 "buy" 命令（商店购买）----
        elif action == "buy":
            if arg.lower() not in shop_things:
                # 特殊处理：卡牌移除（Card Removal）
                if len(arg.split()) > 2 and arg.split()[0] == "card" and arg.split()[1] == "removal":
                    if " ".join(arg.split()[2:]).lower() not in cardlist:
                        debug_print("Could not find card in cardlist:", " ".join(arg.split()[2:]))
                    elif " ".join(arg.split()[2:]).lower() not in cards_in_deck:
                        debug_print("Could not find card attempted to remove in deck:", " ".join(arg.split()[2:]), "Deck:", cards_in_deck)
                    elif "choice_list" in state and "purge" in state["choice_list"]:
                        commands.append(f"choose {state['choice_list'].index('purge')}")
                        commands.append(f"choose {cards_in_deck.index(' '.join(arg.split()[2:]).lower())}")
                        commands.append("confirm")
                        state['choice_list'].remove('purge')
                else:
                    debug_print("Could not find item in shop:", arg.lower(), "Shop items:", shop_things)
            elif "choice_list" in state:
                # 在 choice_list 中找到对应物品的索引
                choice_list_lower = [x.lower() for x in state["choice_list"]]
                if arg.lower() in choice_list_lower:
                    index = choice_list_lower.index(arg.lower())
                    
                    command = "choose " + str(index)
                    commands.append(command)
                    state["choice_list"].pop(index)
                    
                    # 扣除金币
                    for item in state["screen_state"]["cards"] + state["screen_state"]["relics"] + state["screen_state"]["potions"]:
                        if item["name"].lower() == arg.lower():
                            state["gold"] -= item["price"]
                            break

                    # 移除买不起的商品
                    for item in state["screen_state"]["cards"] + state["screen_state"]["relics"] + state["screen_state"]["potions"]:
                        if item["name"].lower() in state["choice_list"] and item["price"] > state["gold"]:
                            state["choice_list"].remove(item["name"].lower())

                    if "purge" in state["choice_list"] and state["screen_state"]["purge_cost"] > state["gold"]:
                        state["choice_list"].remove("purge")
                    
        # ---- 处理 "potion" 命令（使用/丢弃药水）----
        elif action == "potion":
            if arg.split()[0] == "use":
                if arg.split()[1].isdigit() and int(arg.split()[1]) < 3:
                    if len(arg.split()) == 2:
                        arg += " 0"  # 默认目标索引 0
                    commands.append(f"potion use {' '.join(arg.split()[1:])}")
                else:
                    debug_print("Invalid potion slot:", arg.split()[1])
            elif arg.split()[0] == "discard":
                if arg.split()[1].isdigit() and int(arg.split()[1]) < 3:
                    commands.append(f"potion discard {arg.split()[1]}")
                else:
                    debug_print("Invalid potion slot:", arg.split()[1])
        
        # ---- 处理 "skip" 命令（跳过奖励）----
        elif action == "skip":
            commands.append("skip")
            commands.append("proceed")  # skip 后自动 proceed
        else:
            debug_print("Unknown action:", action)

    # ====================================================================
    # 步骤 6：命令后处理
    # ====================================================================
    # 将 "smith" / "rest" 等文本选项转换为数字索引
    i = 0
    for command in commands:
        if command.split()[0] == "choose" and command.split()[1] == "smith":
            commands[i] = f"choose 1"   # 铁匠（升级卡牌）通常是选项 1
        elif command.split()[0] == "choose" and command.split()[1] == "rest":
            commands[i] = f"choose 0"   # 休息（恢复 HP）通常是选项 0
        i += 1

    # 非商店、非战斗场景：按 choose 索引排序
    # 确保 choose 命令按从小到大执行（potion 命令排在最前面）
    if not is_shop and not is_combat:
        commands.sort(key=lambda x: int(x.split()[1]) if x.split()[0] == "choose" else (-999 if x.split()[0] == "potion" else 0))
    
    # 战斗奖励场景：调整 choose 索引（因为每次选择后列表会缩短）
    if is_combat_reward:
        num_found = 0
        i = 0
        for command in commands:
            if command.split()[0] == "choose":
                # 每选一个奖励，后续索引需要减 1
                commands[i] = f"choose {int(command.split()[1]) - num_found}"
                num_found += 1
            i += 1
        commands.append("proceed")  # 选完所有奖励后继续
            
    # 需要确认的场景（如 HAND_SELECT、GRID）追加 confirm 命令
    if requires_confirm:
        commands.append("confirm")
    
    # 商店场景：购买完后离开并继续
    if is_shop:
        commands.append("leave")
        commands.append("proceed")
    
    # Boss 遗物奖励：选完后继续
    if state["screen_type"] == "BOSS_REWARD":
        commands.append("proceed")
    
    # 双重保险：如果 AI 忘记在战斗回合结束时添加 {end}，自动补上
    if is_combat and commands and commands[-1] != "end":
        debug_print("Auto-adding 'end' command to finish combat turn")
        commands.append("end")

    return commands, is_combat