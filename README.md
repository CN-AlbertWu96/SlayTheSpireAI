# Slay the Spire AI

An AI-powered bot that plays Slay the Spire using Tencent Cloud GLM-5 model. The bot reads the game state through Communication Mod and makes intelligent decisions about card plays, pathing, and other in-game choices.

## Requirements

- Python 3.10+
- Slay the Spire with Communication Mod installed
- Miniconda or Anaconda (recommended)

## Quick Start

### 1. Create Virtual Environment

```bash
conda create -n slaythespire python=3.10 -y
conda activate slaythespire
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Communication Mod

1. Subscribe to [Communication Mod on Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=2131373661)
2. Enable the mod in-game (Mods menu)
3. Restart the game

### 4. Configure Communication Mod

The configuration file is located at:
```
C:\Users\Administrator\AppData\Local\ModTheSpire\CommunicationMod\config.properties
```

Set the content to:
```properties
command=C:/Users/Administrator/miniconda3/envs/slaythespire/python.exe C:/Users/Administrator/CodeBuddy/SlayTheSpireAI/main.py
runAtGameStart=true
```

**Note**: Adjust the Python path if your Miniconda is installed in a different location.

### 5. Run the Bot

1. Start Slay the Spire
2. The GUI will automatically launch when the game starts
3. Begin a new game
4. Click "Start" to generate AI decisions
5. Enable "Auto Do Action" for automatic execution

## Configuration

### API Settings

The bot is pre-configured to use Tencent Cloud GLM-5 API:
- **API URL**: `https://api.lkeap.cloud.tencent.com/coding/v3`
- **Model**: `glm-5`
- **API Key**: Pre-configured in `gamestatetooutput.py`

To use a different model or API, edit `gamestatetooutput.py` lines 36-42.

### Game Communication

Communication Mod uses stdin/stdout to communicate:
1. Game sends JSON state to Python script
2. Script calls AI API to generate decisions
3. Script returns commands to game
4. Game executes commands

## Features

- Reads complete game state (cards, enemies, relics, potions)
- Makes intelligent decisions for combat, pathing, rewards, shops
- Real-time GUI showing game state and AI reasoning
- Automatic action execution
- Debug logging

## Files

- `main.py` - Main program and GUI
- `gamestatetooutput.py` - Game state parsing and AI integration
- `requirements.txt` - Python dependencies
- `start.bat` / `start.sh` - Startup scripts (optional)
- `test_config.py` - Communication test script
- `data/` - Game data (cards, relics, potions, powers)

## Troubleshooting

### GUI doesn't launch automatically

1. Check the config file path is correct
2. Verify Python path in config
3. Check game log: `Steam\steamapps\common\SlayTheSpire\mts.log`

### API errors

1. Check network connection
2. Verify API key in `gamestatetooutput.py`
3. Check debug output in GUI

### Communication test

Run the test script to verify setup:
```bash
python test_config.py
```

Check the log file: `communication_test.log`

## License

Do whatever you want
