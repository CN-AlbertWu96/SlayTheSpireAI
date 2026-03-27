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

### 3. Configure API Keys

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```properties
TENCENT_API_KEY=your-api-key-here
TENCENT_API_URL=https://api.lkeap.cloud.tencent.com/coding/v3
TENCENT_MODEL=glm-5
```

**Important**:
- Never commit your `.env` file to version control!
- The program will automatically load environment variables from `.env` when it starts
- Make sure `.env` is in the project root directory (same level as `main.py`)

### 4. Install Communication Mod

1. Subscribe to [Communication Mod on Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=2131373661)
2. Enable the mod in-game (Mods menu)
3. Restart the game

### 5. Configure Communication Mod

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

### 6. Run the Bot

1. Start Slay the Spire
2. The GUI will automatically launch when the game starts
3. Begin a new game
4. Click "Start" to generate AI decisions
5. Enable "Auto Do Action" for automatic execution

## Configuration

### API Settings

The bot uses environment variables for API configuration:
- `TENCENT_API_KEY`: Your Tencent Cloud API key (required)
- `TENCENT_API_URL`: API endpoint (default: https://api.lkeap.cloud.tencent.com/coding/v3)
- `TENCENT_MODEL`: Model name (default: glm-5)
- `CLAUDE_API_KEY`: Claude API key (optional, for using Claude models)

To use a different model, edit the `.env` file.

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
- `.env.example` - Environment variables template
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
2. Verify API key in `.env` file
3. Check debug output in GUI

### Communication test

Run the test script to verify setup:
```bash
python test_config.py
```

Check the log file: `communication_test.log`

## Security Notes

- **Never commit `.env` file** to version control
- Keep your API keys secure
- Use environment variables for sensitive data
- The `.env` file is already in `.gitignore`

## License

Do whatever you want
