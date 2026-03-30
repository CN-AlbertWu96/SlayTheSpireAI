import sys
import os

# ============================================================================
# 第一部分：环境初始化
# ============================================================================
# 这部分在程序启动时最先执行，负责：
# 1. 加载环境变量（API Key 等敏感信息）
# 2. 修复 SSL 证书问题（某些环境下 HTTPS 请求会失败）
# 3. 向游戏发送就绪信号

# 加载 .env 文件中的环境变量
# .env 文件格式示例：
#   OPENAI_API_KEY=sk-xxx
#   ANTHROPIC_API_KEY=sk-ant-xxx
from dotenv import load_dotenv
load_dotenv()

# 修复 SSL 证书环境变量问题
# 某些 Python 环境会设置无效的 SSL_CERT_FILE/SSL_CERT_DIR 环境变量
# 导致 HTTPS 请求失败，需要删除这些无效的环境变量
if 'SSL_CERT_FILE' in os.environ and not os.path.exists(os.environ['SSL_CERT_FILE']):
    del os.environ['SSL_CERT_FILE']
if 'SSL_CERT_DIR' in os.environ and not os.path.exists(os.environ['SSL_CERT_DIR']):
    del os.environ['SSL_CERT_DIR']

# 向 stdout 发送就绪信号
# Communication Mod 会等待这行输出，收到后才开始发送游戏状态
# 注意：flush() 是必须的，因为 stdout 默认有缓冲，不 flush 的话数据可能不会立即发送
print("ready") # not really
sys.stdout.flush()


# ============================================================================
# 第二部分：导入模块和初始化路径
# ============================================================================
import time, threading, datetime, json, traceback, logging

# 获取当前脚本所在目录，并将其加入 Python 模块搜索路径
# 这样就能导入同目录下的 gamestatetooutput 模块
dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path)

# 导入核心模块：将游戏状态转换为 AI 决策的函数
from gamestatetooutput import gamestate_to_output

# 创建日志目录，用于保存每次游戏状态的 JSON 快照
# 这些日志对于调试和理解 AI 决策过程非常重要
logs_path = os.path.join(dir_path, "logs")
if not os.path.exists(logs_path):
    os.makedirs(logs_path)

# 配置日志格式
def get_timestamp():
    """获取当前时间戳，格式：2024-01-15 14:30:25.123"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def main(app):
    """
    后台监听线程的主函数 - 核心事件循环
    
    这个函数在一个独立线程中运行，负责：
    1. 阻塞式读取来自 Communication Mod 的游戏状态 JSON
    2. 解析 JSON 并更新共享状态
    3. 触发命令执行
    
    注意：这个函数必须运行在独立线程中，因为 stdin.readline() 是阻塞调用
    如果在主线程运行，会冻结 GUI
    """
    app.print("Automaton started")
    
    # 主事件循环 - 无限循环直到出错
    while True:
        try:
            # ====================================================================
            # 步骤 1: 阻塞等待游戏状态
            # ====================================================================
            # stdin.readline() 会一直阻塞，直到收到一行数据
            # Communication Mod 每次游戏状态变化都会发送一个 JSON 字符串
            game_state = sys.stdin.readline().strip()
            
            s = f"{game_state}\n\n\n\n\n\n"
            app.print("got game state")
            
            # ====================================================================
            # 步骤 2: 解析 JSON
            # ====================================================================
            # 某些情况下 JSON 中会出现 ",\n        ..." 这样的省略号
            # 需要删除才能正确解析
            jsonified = json.loads(game_state.replace(",\n        ...", ""))
            
            # ====================================================================
            # 步骤 3: 处理游戏状态
            # ====================================================================
            if "error" not in jsonified:
                # 检测游戏状态是否改变（如进入选择界面）
                # 如果 screen_type 改变，应该清空命令队列重新生成
                old_game_state = app.last_game_state
                should_clear_queue = False
                
                if old_game_state:
                    try:
                        old_state = json.loads(old_game_state.replace(",\n        ...", ""))
                        old_screen_type = old_state.get("screen_type", "")
                        new_screen_type = jsonified.get("screen_type", "")
                        
                        # 如果屏幕类型改变，清空队列
                        if old_screen_type != new_screen_type:
                            app.debug_print(f"Screen type changed: {old_screen_type} -> {new_screen_type}")
                            should_clear_queue = True
                        
                        # 或者从战斗中进入特殊界面（如 Headbutt 选择界面）
                        if "combat_state" in old_state and "combat_state" in jsonified:
                            if old_state.get("screen_type") == "" and new_screen_type != "":
                                app.debug_print(f"Entered special screen during combat: {new_screen_type}")
                                should_clear_queue = True
                    except Exception as e:
                        app.debug_print(f"Error comparing game states: {e}")
                
                # 更新共享状态，供其他线程使用
                app.last_game_state = game_state
                
                # 如果需要清空队列，先清空再执行
                if should_clear_queue:
                    app.debug_print("Clearing command queue due to state change")
                    app.queued_commands = []
                
                app.debug_print(f"Updated last_game_state, queued_commands={len(app.queued_commands)}")
                
                # 触发命令执行：
                # - 如果队列中有命令，执行第一个
                # - 如果队列为空，可能触发新的 AI 生成
                app.do_action()
            else:
                app.print("game state contains error")

            # ====================================================================
            # 步骤 4: 保存日志
            # ====================================================================
            # 将游戏状态保存到 logs 目录，格式：03-30_16-52-30.json
            # 这对于调试和理解 AI 决策过程非常有用
            filename = datetime.datetime.now().strftime("%m-%d_%H-%M-%S") + ".json"
            with open(os.path.join(logs_path, filename), "w") as f:
                json.dump(json.loads(game_state), f, indent=4)
        
        except Exception as e:
            # ====================================================================
            # 异常处理：记录错误并退出循环
            # ====================================================================
            s = f"An error occurred: {e}\n\n\n\n\n\n"
            filename = datetime.datetime.now().strftime("%m-%d_%H-%M-%S") + "-ERROR.json"
            with open(os.path.join(logs_path, filename), "w") as f:
                json.dump(json.loads(game_state), f, indent=4)
            app.error_print(f"An error occurred: {e}")
            break



# ============================================================================
# 第三部分：GUI 界面类
# ============================================================================
# 这个类负责：
# 1. 创建和管理 Tkinter GUI 窗口
# 2. 维护游戏状态和命令队列（被多个线程共享）
# 3. 提供日志输出接口
# 4. 处理用户交互（按钮点击、复选框等）

import tkinter as tk
from tkinter import scrolledtext, ttk

class SlayTheSpireModUI:
    def __init__(self, master):
        """
        初始化 GUI 应用
        
        Args:
            master: Tkinter 根窗口对象
        """
        self.master = master
        master.title("Automaton")
        master.geometry("1200x800")
        master.configure(bg='#2b2b2b')  # 深色主题背景
        
        # 设置窗口始终置顶，方便观察 AI 决策过程
        master.attributes('-topmost', True)

        # ====================================================================
        # 核心状态变量 - 被多个线程共享
        # ====================================================================
        self.messages = []           # LLM 对话历史，保持上下文连贯性
        self.last_game_state = None  # 最新的游戏状态 JSON 字符串
        self.queued_commands = []    # 待执行的命令队列，如 ["play Strike 0", "end"]
        self.is_in_combat = False    # 是否在战斗状态，影响自动生成行为

        self.create_widgets()


    def create_widgets(self):
        """创建 GUI 控件：状态栏、文本区域、按钮等"""
        # ====================================================================
        # 状态标题栏
        # ====================================================================
        self.status_label = tk.Label(self.master, text="Status: Idle", font=("Arial", 16, "bold"), bg='#2b2b2b', fg='white')
        self.status_label.pack(pady=10)

        # ====================================================================
        # 主文本区域框架（左右两栏）
        # ====================================================================
        main_frame = tk.Frame(self.master, bg='#2b2b2b')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：主日志文本框 - 显示 INFO 级别日志
        self.main_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=30, bg='#1e1e1e', fg='white')
        self.main_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 右侧：调试日志文本框 - 显示 DEBUG/ERROR 级别日志
        self.debug_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=40, height=30, bg='#1e1e1e', fg='#00ff00')
        self.debug_text.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # ====================================================================
        # 控制按钮区域
        # ====================================================================
        control_frame = tk.Frame(self.master, bg='#2b2b2b')
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        # [Do Action] 按钮：手动执行下一个命令
        self.do_action_button = tk.Button(control_frame, text="Do Action", command=self.do_action)
        self.do_action_button.pack(side=tk.LEFT, padx=(0, 10))

        # [Auto Do Action] 复选框：是否自动执行命令
        # 开启后，AI 生成的命令会自动逐个执行
        self.auto_do_action_var = tk.BooleanVar()
        self.auto_do_action_check = tk.Checkbutton(control_frame, text="Auto Do Action", variable=self.auto_do_action_var, bg='#2b2b2b', fg='white', selectcolor='#1e1e1e')
        self.auto_do_action_check.pack(side=tk.LEFT, padx=(0, 20))

        # [Start/Stop] 按钮：手动触发 AI 生成或停止
        self.start_stop_button = tk.Button(control_frame, text="Start", command=self.toggle_start_stop)
        self.start_stop_button.pack(side=tk.LEFT, padx=(0, 10))

        # [Auto Generate] 复选框：是否自动生成命令
        # 开启后，命令队列空时会自动触发 AI 生成新命令
        self.auto_generate_var = tk.BooleanVar(value=True)  # 默认开启
        self.auto_generate_check = tk.Checkbutton(control_frame, text="Auto Generate", variable=self.auto_generate_var, bg='#2b2b2b', fg='white', selectcolor='#1e1e1e')
        self.auto_generate_check.pack(side=tk.LEFT)


    def print(self, *text):
        """
        INFO 级别日志 - 输出到主文本框
        
        Args:
            *text: 可变参数，会被空格连接成一个字符串
        """
        timestamp = get_timestamp()
        message = " ".join([str(x) for x in text])
        formatted = f"[{timestamp}] [INFO] {message}"
        self.main_text.insert(tk.END, formatted + '\n')
        self.main_text.see(tk.END)  # 自动滚动到最新内容

    def debug_print(self, *text):
        """
        DEBUG 级别日志 - 输出到调试文本框
        
        Args:
            *text: 可变参数，会被空格连接成一个字符串
        """
        timestamp = get_timestamp()
        message = " ".join([str(x) for x in text])
        formatted = f"[{timestamp}] [DEBUG] {message}"
        self.debug_text.insert(tk.END, formatted + '\n')
        self.debug_text.see(tk.END)

    def error_print(self, *text):
        """
        ERROR 级别日志 - 输出到调试文本框（与 DEBUG 同区域）
        
        Args:
            *text: 可变参数，会被空格连接成一个字符串
        """
        timestamp = get_timestamp()
        message = " ".join([str(x) for x in text])
        formatted = f"[{timestamp}] [ERROR] {message}"
        self.debug_text.insert(tk.END, formatted + '\n')
        self.debug_text.see(tk.END)

    def set_status(self, status):
        """更新状态栏显示"""
        self.status_label.config(text=f"Status: {status}")


    def do_action(self):
        """
        执行命令队列中的下一个命令 - 核心命令执行引擎
        
        这个函数负责：
        1. 从命令队列中取出第一个命令
        2. 如果是 "play" 命令，将卡牌名称转换为手牌索引
        3. 将命令发送到 stdout 给游戏执行
        4. 如果队列为空，可能触发新的 AI 生成
        
        命令格式示例：
        - "play Strike 0" -> 出牌 "Strike"，目标是敌人 0
        - "end" -> 结束回合
        - "choose 1" -> 选择选项 1（在地图、商店等界面）
        """
        if len(self.queued_commands) > 0:
            # =================================================================
            # 步骤 1: 从队列头部取出一个命令
            # =================================================================
            command = self.queued_commands.pop(0)
            
            # =================================================================
            # 步骤 2: 处理 "play" 命令 - 需要将卡牌名称转换为手牌索引
            # =================================================================
            # Communication Mod 需要的格式是 "play <手牌索引> <目标索引>"
            # 例如："play 1 0" 表示打出第 1 张牌，目标是敌人 0
            # 但 AI 返回的是 "play Strike 0"，需要转换
            if command.split()[0] == "play":
                if self.last_game_state is None:
                    self.debug_print("M: No game state available. Skipping action: " + command)
                    return
                
                # 解析游戏状态 JSON
                state = json.loads(self.last_game_state.replace(",\n        ...", ""))
                
                # 检查是否在游戏中
                if "in_game" in state:
                    if not state["in_game"]:
                        self.debug_print("M: Not in game. Skipping action: " + command)
                        return
                
                # 处理嵌套的游戏状态结构
                if "relics" not in state:
                    state = state["game_state"]
                
                # 获取当前手牌列表（小写）
                hand = [card["name"].lower() for card in state["combat_state"]["hand"]]
                
                # 从命令中提取卡牌名称
                # 例如 "play Strike 0" -> "strike"
                card_to_play = " ".join(command.split()[1:-1]).lower()
                
                # 检查卡牌是否在手牌中
                if card_to_play not in hand:
                    self.debug_print(f"M: Card {card_to_play} not in hand. Skipping action: {command}")
                    return
                else:
                    # 转换命令格式：
                    # "play Strike 0" -> "play 1 0"（假设 Strike 是第 1 张牌）
                    command = f"play {hand.index(card_to_play)+1} {command.split()[-1]}"

            # =================================================================
            # 步骤 3: 发送命令到 stdout 给游戏执行
            # =================================================================
            self.print("Performing action: " + command)
            print(command)  # 发送到 stdout
            sys.stdout.flush()  # 立即刷新缓冲区
        else:
            # =================================================================
            # 步骤 4: 命令队列为空，可能触发新的 AI 生成
            # =================================================================
            self.debug_print("No more queued commands")
            self.debug_print(f"auto_generate={self.auto_generate_var.get()}, is_in_combat={self.is_in_combat}")
            
            # 如果开启了自动生成，触发新一轮 AI 决策
            if self.auto_generate_var.get():
                self.debug_print("Auto generating commands for new game state...")
                self.toggle_start_stop()
            
            # 清空命令队列（防止残留）
            self.queued_commands = []
            
        # =====================================================================
        # 特殊处理：非战斗状态下的自动生成
        # =====================================================================
        # 如果不在战斗中（在地图、商店等界面），延迟 1 秒后自动生成新命令
        # 这样可以自动处理地图选择、商店购买等非战斗场景
        if self.auto_generate_var.get() and not self.is_in_combat:
            time.sleep(1)
            self.toggle_start_stop()
        


    def toggle_start_stop(self):
        """
        切换 AI 生成状态 - 启动或停止
        
        这个函数负责：
        1. 检查是否可以开始新的生成
        2. 更新 UI 状态（按钮文本、状态栏）
        3. 在新线程中启动 AI API 调用
        
        注意：API 调用必须在独立线程中执行，否则会冻结 GUI
        """
        self.debug_print(f"toggle_start_stop called, last_game_state={'exists' if self.last_game_state else 'None'}")
        
        # 检查是否有游戏状态可用
        if self.last_game_state is None:
            self.debug_print("last game state is none")
            return
        
        # 检查当前按钮状态，防止重复启动
        current_button_text = self.start_stop_button.cget('text')
        self.debug_print(f"Button state: {current_button_text}")
        if current_button_text == 'Stop':
            self.debug_print("Not finished generating. Can't start new generation.")
            return
        
        # 更新 UI 状态
        self.start_stop_button.config(text='Stop')
        self.set_status("Generating...")
        self.debug_print("Starting API call in background thread...")

        # =====================================================================
        # 在新线程中执行 API 调用，避免阻塞 GUI
        # =====================================================================
        def generate_commands():
            """
            API 工作线程函数 - 调用 LLM API 生成命令
            
            这个函数运行在独立线程中，负责：
            1. 调用 gamestate_to_output() 获取 AI 决策
            2. 处理返回结果（命令列表 + 是否在战斗中）
            3. 通过 master.after() 将 UI 更新调度到主线程
            """
            try:
                self.debug_print("Thread started, calling gamestate_to_output...")
                start_time = time.time()
                
                # 调用核心函数：将游戏状态转换为命令列表
                result = gamestate_to_output(self.last_game_state, self.print, self.debug_print, self.messages)
                
                elapsed_time = time.time() - start_time
                
                # 解构返回值：
                # gamestate_to_output 返回一个元组 (commands, is_combat)
                # - commands: 命令列表，如 ["play Strike 0", "end"]
                # - is_combat: 是否在战斗中
                if isinstance(result, tuple):
                    commands, is_combat = result
                else:
                    commands = result
                    is_combat = False
                
                self.is_in_combat = is_combat
                self.debug_print(f"API call completed in {elapsed_time:.2f}s, got {len(commands)} commands, is_combat={is_combat}")
                
            except Exception as e:
                # 异常处理：记录错误信息
                stack_trace = traceback.format_exc()
                self.error_print(f"An error occurred in the gamestate_to_output func: {e}")
                self.debug_print(f"Full stack trace:\n{stack_trace}")
                commands = []
                self.is_in_combat = False

            # =================================================================
            # 关键：在主线程中更新 UI
            # =================================================================
            # Tkinter 不允许非主线程直接操作 UI
            # 必须使用 master.after(0, callback) 将 UI 更新"调度"到主线程
            # after(0, ...) 表示立即在主线程中执行回调
            self.debug_print("Scheduling UI update on main thread...")
            self.master.after(0, lambda: self.finish_generation(commands))

        # 创建并启动守护线程
        # daemon=True 表示当主线程退出时，这个线程会自动终止
        thread = threading.Thread(target=generate_commands, daemon=True)
        thread.start()
        self.debug_print(f"Background thread started: {thread.name}")


    def finish_generation(self, commands):
        """
        完成 AI 生成后更新 UI - 在主线程中执行
        
        这个函数由 generate_commands() 线程通过 master.after() 调度到主线程执行
        负责：
        1. 更新 UI 状态（按钮文本、状态栏）
        2. 将生成的命令放入队列
        3. 如果开启了自动执行，触发第一个命令的执行
        
        Args:
            commands: AI 生成的命令列表，如 ["play Strike 0", "end"]
        """
        self.debug_print(f"finish_generation called, got {len(commands)} commands")
        
        # 更新 UI 状态
        self.start_stop_button.config(text='Start')
        self.set_status("Idle")

        # 将命令放入队列，供 do_action() 使用
        self.queued_commands = commands
        self.print("Actions:", commands)
        self.debug_print(f"UI updated, {len(commands)} commands queued, auto_do_action={self.auto_do_action_var.get()}")

        # 如果开启了自动执行，立即执行第一个命令
        if self.auto_do_action_var.get():
            self.debug_print("Auto executing first command...")
            self.do_action()

# ============================================================================
# 第四部分：程序入口
# ============================================================================
# 这是整个程序的启动点，展示了三线程协作模型：
# 1. 主线程：运行 GUI 事件循环 (root.mainloop())
# 2. 后台监听线程：阻塞读取 stdin，接收游戏状态
# 3. API 工作线程：调用 LLM API 生成决策（按需创建）

if __name__ == "__main__":
    # 步骤 1: 创建 Tkinter 根窗口
    root = tk.Tk()
    
    # 步骤 2: 创建应用对象，初始化 GUI 和状态
    app = SlayTheSpireModUI(root)
    
    # 步骤 3: 启动后台监听线程
    # 这个线程负责阻塞读取 stdin，接收来自 Communication Mod 的游戏状态
    # 注意：必须在独立线程中运行，因为 stdin.readline() 是阻塞调用
    threading.Thread(target=main, args=(app,)).start()
    
    # 步骤 4: 进入 GUI 主事件循环
    # 程序会在这里一直运行，直到窗口关闭
    # 所有 GUI 事件（点击、键盘等）都在这个循环中处理
    root.mainloop()