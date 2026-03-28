import json, anthropic, re, os, sys, openai

dir_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data")

with open(os.path.join(dir_path, "cardlist.json"), "r", encoding="utf-8") as f:
    cardlist = json.load(f)

with open(os.path.join(dir_path, "powerlist.json"), "r", encoding="utf-8") as f:
    powerlist = json.load(f)

with open(os.path.join(dir_path, "reliclist.json"), "r", encoding="utf-8") as f:
    reliclist = json.load(f)

with open(os.path.join(dir_path, "potionlist.json"), "r", encoding="utf-8") as f:
    potionlist = json.load(f)


cardlist = {k.lower(): v for k, v in cardlist.items()}
powerlist = {k.lower(): v for k, v in powerlist.items()}
reliclist = {k.lower(): v for k, v in reliclist.items()}
potionlist = {k.lower(): v for k, v in potionlist.items()}

# Claude客户端（仅在需要时初始化）
claude_client = None

def get_claude_client():
    """延迟初始化Claude客户端"""
    global claude_client
    if claude_client is None and os.getenv("CLAUDE_API_KEY"):
        try:
            claude_client = anthropic.Client(api_key=os.getenv("CLAUDE_API_KEY"))
        except Exception as e:
            print(f"Warning: Failed to initialize Claude client: {e}")
    return claude_client

# 腾讯云Code Plan API配置
# 从环境变量读取API配置
TENCENT_API_KEY = os.getenv("TENCENT_API_KEY")
TENCENT_API_URL = os.getenv("TENCENT_API_URL", "https://api.lkeap.cloud.tencent.com/coding/v3")

if not TENCENT_API_KEY:
    raise ValueError("TENCENT_API_KEY environment variable not set. Please set it before running the bot.")

openai_client = openai.Client(
    api_key=TENCENT_API_KEY,
    base_url=TENCENT_API_URL
)

model = os.getenv("TENCENT_MODEL", "hunyuan-turbos")

"""
"claude-3-5-sonnet-20240620"
"""

def GPT(messages, model=model):
    if "claude" in model:
        client = get_claude_client()
        if client is None:
            raise ValueError("Claude API key not configured. Please set CLAUDE_API_KEY environment variable.")
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0,
            messages=messages
        )
        
        return response.content[0].text
    else:
        response = openai_client.chat.completions.create(
            model=model,
            max_tokens=2000,
            temperature=0,
            messages=messages
        )

        return response.choices[0].message.content

def gamestate_to_output(input_json, print, debug_print, messages=[]):
    state = json.loads(input_json.replace(",\n        ...", ""))

    if "in_game" in state:
        if not state["in_game"]:
            debug_print("Not in game")
            return [], False

    keep_messages = False

    if "relics" not in state:
        state = state["game_state"]

    if "choice_list" in state and len(state["choice_list"]) == 1 and state["screen_type"] == "SHOP_ROOM":
        return ["choose 0"], False

    map_dict = {
        "M": "Normal Enemy",
        "E": "Elite Enemy",
        "$": "Shop",
        "?": "?",
        "R": "Rest Site",
        "T": "Treasure",
    }

    potions_str = ""
    for potion in state["potions"]:
        # 支持中英文药水栏名称
        if potion["name"] not in ["Potion Slot", "药水栏"]:
            if potion['name'].lower() not in potionlist:
                debug_print("Unknown potion:", potion['name'])
            potions_str += f"{potion['name']}: {potionlist[potion['name'].lower()]}\n"
        else:
            potions_str += "Empty Slot\n"


    relics_str = ""
    for relic in state["relics"]:
        if relic['name'].lower() not in reliclist:
            debug_print("Unknown relic:", relic['name'])
        if relic["counter"] >= -1:
            counter = f" (Counter: {relic['counter']})" if relic["counter"] > -1 else ""
            relics_str += f"{relic['name']}{counter}: {reliclist[relic['name'].lower()]}\n"


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
    cards_in_deck = []
    if "combat_state" not in state:
        prompt += "Deck:\n"
        for card in state["deck"]:
            if card["name"].lower() not in cardlist:
                debug_print("Unknown card:", card["name"])
            else:
                prompt += f"{card['name']} ({'X' if card['cost'] == -1 else (card['cost'] if card['cost'] != -2 else 'Unplayable')} Energy)\n"
                cards_in_deck.append(card["name"].lower())
    prompt += "\n\n\n\n"

    combat_hand = []
    shop_things = []
    requires_confirm = False
    is_combat_reward = False
    is_combat = False
    is_shop = False

    if "next_nodes" in state["screen_state"]:
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

    elif state["screen_type"] == "HAND_SELECT":
        requires_confirm = True
        keep_messages = True
        choices = state.get("choice_list", [])
        prompt = f"Select cards.\nOptions: {', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}}"

    elif "combat_state" in state:
        is_combat = True
        if state["screen_type"] == "CARD_REWARD":
            requires_confirm = True
            keep_messages = True
            choices = state.get("choice_list", [])
            prompt = f"Card Reward (choose one):\n{', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}} or {{skip}}"
        else:
            unique_cards = set()

            def pile_to_str(pile, fill_combat_hand=False):
                pile_str = ""
                for card in pile:
                    if fill_combat_hand:
                        combat_hand.append(card["name"])
                        unique_cards.add(card["name"].lower())
                    pile_str += f"{card['name']} ({'X' if card['cost'] == -1 else (card['cost'] if card['cost'] != -2 else 'Unplayable')}) "
                if pile_str == "":
                    pile_str = "Empty"
                return pile_str.strip()
            
            draw_pile = pile_to_str(state["combat_state"]["draw_pile"])
            discard_pile = pile_to_str(state["combat_state"]["discard_pile"])
            hand = pile_to_str(state["combat_state"]["hand"], fill_combat_hand=True)

            # 只发送手牌中的卡牌描述
            card_descriptions = ""
            for card in combat_hand:
                card_lower = card.lower()
                if card_lower in cardlist:
                    card_descriptions += f"{card}: {cardlist[card_lower]}\n"

            monsters = ""
            i = 0
            for monster in state["combat_state"]["monsters"]:
                if not monster["is_gone"]:
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

                    for power in monster['powers']:
                        if power['name'].lower() not in powerlist:
                            debug_print("Unknown power:", power['name'])
                            monster['powers'].remove(power)

                    powers_str = ", ".join([f"{power['amount']} {power['name']}" for power in monster['powers']]) if monster['powers'] else "None"
                    monsters += f"[{i}] {monster['name']}: {monster['current_hp']}/{monster['max_hp']}HP, {monster['block']} block, Intent: {intent}, Powers: {powers_str}\n"

                i += 1

            player_powers = ""
            for power in state["combat_state"]["player"]["powers"]:
                if power['name'].lower() not in powerlist:
                    debug_print("Unknown power:", power['name'])
                else:
                    player_powers += f"{power['amount']} {power['name']}, "
            if player_powers:
                player_powers = f"\nYour Powers: {player_powers.strip(', ')}"

            prompt += f"""Combat State:
Energy: {state["combat_state"]["player"]["energy"]}
Hand: {hand}
Draw Pile: {draw_pile}
Discard Pile: {discard_pile}{player_powers}

Enemies:
{monsters}
Card Effects:
{card_descriptions}
Actions: {{play CardName target}} {{end}} {{potion use/discard slot target}}
Rules: Only play cards in hand. Check energy. Use {{}} only for actions."""

    elif state["screen_type"] == "SHOP_SCREEN":
        is_shop = True
        cards = ""
        relics = ""
        potions = ""
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
    
    elif state["screen_type"] == "REST_SITE":
        choices = {}
        for option in state["screen_state"]["options"]:
            choices[option["label"]] = option["choice_index"]
        
        if len(choices) == 1:
            return ["choose 0"], False

        prompt += f"Rest Site. HP: {state['current_hp']}/{state['max_hp']}\nOptions: {', '.join([f'{i}: {k}' for i, k in enumerate(choices.keys())])}\nAction: {{choose index}}"
            
    elif state["screen_type"] == "CARD_REWARD":
        cards = ""
        for card in state["screen_state"]["cards"]:
            if card["name"].lower() not in cardlist:
                debug_print("Unknown card:", card["name"])
            cards += f"{card['name']} ({'X' if card['cost'] == -1 else (card['cost'] if card['cost'] != -2 else 'Unplayable')} Energy): {cardlist[card['name'].lower()]}\n"
        prompt += f"Card Reward:\n{cards}Action: {{choose index}} or {{skip}}"
    
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
        
    elif state["screen_type"] == "GRID":
        requires_confirm = True
        keep_messages = True
        choices = state.get("choice_list", [])
        
        prompt = f"Grid selection:\n{', '.join([f'{i}: {c}' for i, c in enumerate(choices)])}\nAction: {{choose index}}"
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
    
    elif state["screen_type"] == "CHEST":
        if not state["screen_state"]["chest_open"]:
            return ["choose 0"], False
    
    elif state["screen_type"] == "BOSS_REWARD":
        relics = ""
        for relic in state["screen_state"]["relics"]:
            if relic["name"].lower() not in reliclist:
                debug_print("Unknown relic:", relic["name"])
            else:
                relics += f"{relic['name']}: {reliclist[relic['name'].lower()]}\n"
        prompt += f"Boss Relic (choose one):\n{relics}Action: {{choose index}} or {{skip}}"
    else:
        debug_print("Unknown screen type:", state["screen_type"])
        return [], False

    if not keep_messages:
        while len(messages) > 0:
            messages.pop()

    print("Generating with prompt:\n" + prompt + "\n\n\n")
    messages.append({"role": "user", "content": prompt})
    
    try:
        response = GPT(messages)
        if not response or response.strip() == "":
            debug_print("API returned empty response, retrying...")
            response = GPT(messages)
    except Exception as e:
        debug_print(f"API call failed: {e}")
        return [], False
    
    if not response or response.strip() == "":
        debug_print("API returned empty response after retry")
        return [], False
    
    messages.append({"role": "assistant", "content": response})
    print("Response:\n" + response + "\n\n\n")

    matches = re.findall(r"\{(.*?)\}", response)
    commands = []
    for match in matches:
        command = None
        action = match.split()[0]
        arg = " ".join(match.split()[1:])
        if action == "play":
            target = ""
            # 移除"target"关键字（如果存在）
            arg_parts = arg.split()
            if "target" in arg_parts:
                arg_parts.remove("target")
                arg = " ".join(arg_parts)
            
            if arg.split()[-1].isdigit():
                target = int(arg.split()[-1])
                arg = " ".join(arg.split()[:-1])
            else:
                i = 0
                for m in state["combat_state"]["monsters"]:
                    if not m["is_gone"]:
                        target = i
                        break
                    i += 1
            if arg not in combat_hand:
                debug_print("Could not find card in hand:", arg, "Hand:", combat_hand)

            command = f"play {arg} {target}"
            commands.append(command)
            #combat_hand.remove(arg)

        elif action == "choose":
            commands.append("choose " + arg)
        elif action == "end":
            commands.append(action)
        elif action == "buy":
            if arg.lower() not in shop_things:
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
                choice_list_lower = [x.lower() for x in state["choice_list"]]
                if arg.lower() in choice_list_lower:
                    index = choice_list_lower.index(arg.lower())
                    
                    command = "choose " + str(index)
                    commands.append(command)
                    state["choice_list"].pop(index)
                    for item in state["screen_state"]["cards"] + state["screen_state"]["relics"] + state["screen_state"]["potions"]:
                        if item["name"].lower() == arg.lower():
                            state["gold"] -= item["price"]
                            break

                    for item in state["screen_state"]["cards"] + state["screen_state"]["relics"] + state["screen_state"]["potions"]:
                        if item["name"].lower() in state["choice_list"] and item["price"] > state["gold"]:
                            state["choice_list"].remove(item["name"].lower())

                    if "purge" in state["choice_list"] and state["screen_state"]["purge_cost"] > state["gold"]:
                        state["choice_list"].remove("purge")
                    
        elif action == "potion":
            if arg.split()[0] == "use":
                if arg.split()[1].isdigit() and int(arg.split()[1]) < 3:
                    if len(arg.split()) == 2:
                        arg += " 0"
                    commands.append(f"potion use {' '.join(arg.split()[1:])}")
                else:
                    debug_print("Invalid potion slot:", arg.split()[1])
            elif arg.split()[0] == "discard":
                if arg.split()[1].isdigit() and int(arg.split()[1]) < 3:
                    commands.append(f"potion discard {arg.split()[1]}")
                else:
                    debug_print("Invalid potion slot:", arg.split()[1])
        elif action == "skip":
            commands.append("skip")
            commands.append("proceed")
        else:
            debug_print("Unknown action:", action)

    i = 0
    for command in commands:
        if command.split()[0] == "choose" and command.split()[1] == "smith":
            commands[i] = f"choose 1"
        elif command.split()[0] == "choose" and command.split()[1] == "rest":
            commands[i] = f"choose 0"
        i += 1

    if not is_shop and not is_combat:
        commands.sort(key=lambda x: int(x.split()[1]) if x.split()[0] == "choose" else (-999 if x.split()[0] == "potion" else 0))
    if is_combat_reward:
        num_found = 0
        i = 0
        for command in commands:
            if command.split()[0] == "choose":
                commands[i] = f"choose {int(command.split()[1]) - num_found}"
                num_found += 1
            i += 1
        commands.append("proceed")
            
    if requires_confirm:
        commands.append("confirm")
    if is_shop:
        commands.append("leave")
        commands.append("proceed")
    if state["screen_type"] == "BOSS_REWARD":
        commands.append("proceed")

    return commands, is_combat