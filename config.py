# config.py
# Configurações do Bot de Legendas do Telegram

# Token do bot obtido do BotFather
BOT_TOKEN = ""

# Configurações opcionais
MAX_FILES_PER_SESSION = 10
MIN_CAPTIONS_REQUIRED = 10

# Configurações de logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Mensagem de boas-vindas
WELCOME_MESSAGE = "Envie seus arquivos para renomear ou use o botão abaixo para adicionar um arquivo JSON contendo legenda."

# Configurações de arquivo
SUPPORTED_JSON_EXTENSIONS = ['.json']
MAX_FILE_SIZE_MB = 20
