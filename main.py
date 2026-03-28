import sys
import os

# 加载.env文件中的环境变量
from dotenv import load_dotenv
load_dotenv()

# 修复SSL证书环境变量问题
if 'SSL_CERT_FILE' in os.environ and not os.path.exists(os.environ['SSL_CERT_FILE']):
    del os.environ['SSL_CERT_FILE']
if 'SSL_CERT_DIR' in os.environ and not os.path.exists(os.environ['SSL_CERT_DIR']):
    del os.environ['SSL_CERT_DIR']

print("ready") # not really
sys.stdout.flush()

import time, threading, datetime, json, traceback, logging

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path)

from gamestatetooutput import gamestate_to_output

logs_path = os.path.join(dir_path, "logs")
if not os.path.exists(logs_path):
    os.makedirs(logs_path)

# 配置日志格式
def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def main(app):
    app.print("Automaton started")
    while True:
        try:
            game_state = sys.stdin.readline().strip()
            
            s = f"{game_state}\n\n\n\n\n\n"
            app.print("got game state")
            jsonified = json.loads(game_state.replace(",\n        ...", ""))
            if "error" not in jsonified:
                app.last_game_state = game_state
                app.debug_print(f"Updated last_game_state, queued_commands={len(app.queued_commands)}")
                app.do_action()
            else:
                app.print("game state contains error")

            filename = datetime.datetime.now().strftime("%m-%d_%H-%M-%S") + ".json"
            with open(os.path.join(logs_path, filename), "w") as f:
                json.dump(json.loads(game_state), f, indent=4)
        
        except Exception as e:
            s = f"An error occurred: {e}\n\n\n\n\n\n"
            filename = datetime.datetime.now().strftime("%m-%d_%H-%M-%S") + "-ERROR.json"
            with open(os.path.join(logs_path, filename), "w") as f:
                json.dump(json.loads(game_state), f, indent=4)
            app.error_print(f"An error occurred: {e}")
            break


import tkinter as tk
from tkinter import scrolledtext, ttk

class SlayTheSpireModUI:
    def __init__(self, master):
        self.master = master
        master.title("Automaton")
        master.geometry("1200x800")
        master.configure(bg='#2b2b2b')
        
        # 设置窗口始终置顶
        master.attributes('-topmost', True)

        self.messages = []
        self.last_game_state = None
        self.queued_commands = []
        self.is_in_combat = False

        self.create_widgets()

    def create_widgets(self):
        # Status Title
        self.status_label = tk.Label(self.master, text="Status: Idle", font=("Arial", 16, "bold"), bg='#2b2b2b', fg='white')
        self.status_label.pack(pady=10)

        # Main frame for text areas
        main_frame = tk.Frame(self.master, bg='#2b2b2b')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Main Text Area
        self.main_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=30, bg='#1e1e1e', fg='white')
        self.main_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Debug Text Area
        self.debug_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=40, height=30, bg='#1e1e1e', fg='#00ff00')
        self.debug_text.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Control Frame
        control_frame = tk.Frame(self.master, bg='#2b2b2b')
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        # Do Action Button
        self.do_action_button = tk.Button(control_frame, text="Do Action", command=self.do_action)
        self.do_action_button.pack(side=tk.LEFT, padx=(0, 10))

        # Auto Do Action Checkbox
        self.auto_do_action_var = tk.BooleanVar()
        self.auto_do_action_check = tk.Checkbutton(control_frame, text="Auto Do Action", variable=self.auto_do_action_var, bg='#2b2b2b', fg='white', selectcolor='#1e1e1e')
        self.auto_do_action_check.pack(side=tk.LEFT, padx=(0, 20))

        # Start/Stop Button
        self.start_stop_button = tk.Button(control_frame, text="Start", command=self.toggle_start_stop)
        self.start_stop_button.pack(side=tk.LEFT, padx=(0, 10))

        # Auto Generate Checkbox (默认开启)
        self.auto_generate_var = tk.BooleanVar(value=True)
        self.auto_generate_check = tk.Checkbutton(control_frame, text="Auto Generate", variable=self.auto_generate_var, bg='#2b2b2b', fg='white', selectcolor='#1e1e1e')
        self.auto_generate_check.pack(side=tk.LEFT)

    def print(self, *text):
        """INFO级别日志 - 输出到主文本框"""
        timestamp = get_timestamp()
        message = " ".join([str(x) for x in text])
        formatted = f"[{timestamp}] [INFO] {message}"
        self.main_text.insert(tk.END, formatted + '\n')
        self.main_text.see(tk.END)

    def debug_print(self, *text):
        """DEBUG级别日志 - 输出到调试文本框"""
        timestamp = get_timestamp()
        message = " ".join([str(x) for x in text])
        formatted = f"[{timestamp}] [DEBUG] {message}"
        self.debug_text.insert(tk.END, formatted + '\n')
        self.debug_text.see(tk.END)

    def error_print(self, *text):
        """ERROR级别日志 - 输出到调试文本框"""
        timestamp = get_timestamp()
        message = " ".join([str(x) for x in text])
        formatted = f"[{timestamp}] [ERROR] {message}"
        self.debug_text.insert(tk.END, formatted + '\n')
        self.debug_text.see(tk.END)

    def set_status(self, status):
        self.status_label.config(text=f"Status: {status}")

    def do_action(self):
        if len(self.queued_commands) > 0:
            command = self.queued_commands.pop(0)
            if command.split()[0] == "play":
                if self.last_game_state is None:
                    self.debug_print("M: No game state available. Skipping action: " + command)
                    return
                state = json.loads(self.last_game_state.replace(",\n        ...", ""))
                if "in_game" in state:
                    if not state["in_game"]:
                        self.debug_print("M: Not in game. Skipping action: " + command)
                        return
                if "relics" not in state:
                    state = state["game_state"]
                
                hand = [card["name"].lower() for card in state["combat_state"]["hand"]]
                card_to_play = " ".join(command.split()[1:-1]).lower()
                if card_to_play not in hand:
                    self.debug_print(f"M: Card {card_to_play} not in hand. Skipping action: {command}")
                    return
                else:
                    command = f"play {hand.index(card_to_play)+1} {command.split()[-1]}"

            self.print("Performing action: " + command)
            print(command)
            sys.stdout.flush()
        else:
            self.debug_print("No more queued commands")
            self.debug_print(f"auto_generate={self.auto_generate_var.get()}, is_in_combat={self.is_in_combat}")
            if self.auto_generate_var.get():
                self.debug_print("Auto generating commands for new game state...")
                self.toggle_start_stop()
            
            self.queued_commands = []
            
        if self.auto_generate_var.get() and not self.is_in_combat:
            time.sleep(1)
            self.toggle_start_stop()
        

    def toggle_start_stop(self):
        self.debug_print(f"toggle_start_stop called, last_game_state={'exists' if self.last_game_state else 'None'}")
        if self.last_game_state is None:
            self.debug_print("last game state is none")
            return
        
        current_button_text = self.start_stop_button.cget('text')
        self.debug_print(f"Button state: {current_button_text}")
        if current_button_text == 'Stop':
            self.debug_print("Not finished generating. Can't start new generation.")
            return
        
        self.start_stop_button.config(text='Stop')
        self.set_status("Generating...")
        self.debug_print("Starting API call in background thread...")

        # 在新线程中执行API调用，避免阻塞GUI
        def generate_commands():
            try:
                self.debug_print("Thread started, calling gamestate_to_output...")
                start_time = time.time()
                result = gamestate_to_output(self.last_game_state, self.print, self.debug_print, self.messages)
                elapsed_time = time.time() - start_time
                # 解构元组：gamestate_to_output返回(commands, is_combat)
                if isinstance(result, tuple):
                    commands, is_combat = result
                else:
                    commands = result
                    is_combat = False
                self.is_in_combat = is_combat
                self.debug_print(f"API call completed in {elapsed_time:.2f}s, got {len(commands)} commands, is_combat={is_combat}")
            except Exception as e:
                stack_trace = traceback.format_exc()
                self.error_print(f"An error occurred in the gamestate_to_output func: {e}")
                self.debug_print(f"Full stack trace:\n{stack_trace}")
                commands = []
                self.is_in_combat = False

            # 在主线程中更新UI
            self.debug_print("Scheduling UI update on main thread...")
            self.master.after(0, lambda: self.finish_generation(commands))

        thread = threading.Thread(target=generate_commands, daemon=True)
        thread.start()
        self.debug_print(f"Background thread started: {thread.name}")

    def finish_generation(self, commands):
        """完成生成后更新UI"""
        self.debug_print(f"finish_generation called, got {len(commands)} commands")
        self.start_stop_button.config(text='Start')
        self.set_status("Idle")

        # 保留 last_game_state 供 do_action 使用
        self.queued_commands = commands
        self.print("Actions:", commands)
        self.debug_print(f"UI updated, {len(commands)} commands queued, auto_do_action={self.auto_do_action_var.get()}")

        if self.auto_do_action_var.get():
            self.debug_print("Auto executing first command...")
            self.do_action()

if __name__ == "__main__":
    root = tk.Tk()
    app = SlayTheSpireModUI(root)
    threading.Thread(target=main, args=(app,)).start()
    root.mainloop()