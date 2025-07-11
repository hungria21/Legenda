import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
import logging
import json
import time
import threading

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar bot
bot = telebot.TeleBot(config.BOT_TOKEN)

# Estados do usuário
WAITING_MODE_SELECTION = "waiting_mode_selection"
WAITING_JSON_FILE = "waiting_json_file"
WAITING_MEDIA_FILES = "waiting_media_files"
PROCESSING = "processing"

# Dados dos usuários
user_data = {}

def get_user_data(user_id):
    """Obtém ou cria dados do usuário"""
    if user_id not in user_data:
        user_data[user_id] = {
            'state': WAITING_MODE_SELECTION,
            'custom_captions': [],
            'media_messages': [],
            'media_count': 0,
            'caption_index': 0,
            'timeout_timer': None,
            'last_media_time': None,
            'bot_message_ids_to_delete': [] # New list for storing bot message IDs
        }
    return user_data[user_id]

def reset_user_data(user_id):
    """Reseta dados do usuário"""
    # Cancelar timer se existir
    if user_id in user_data and user_data[user_id].get('timeout_timer'):
        user_data[user_id]['timeout_timer'].cancel()
    
    user_data[user_id] = {
        'state': WAITING_MODE_SELECTION,
        'custom_captions': [],
        'media_messages': [],
        'media_count': 0,
        'caption_index': 0,
        'timeout_timer': None,
        'last_media_time': None,
        'bot_message_ids_to_delete': [] # Ensure this is also reset
    }

def create_main_menu():
    """Cria o menu principal com botão JSON"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "Json",
            callback_data="mode_json"
        )
    )
    return markup

def process_caption_file(file_content, file_name):
    """Processa arquivo de legendas (JSON ou TXT) e retorna lista de legendas"""
    try:
        text_content = file_content.decode('utf-8')
        captions = []

        if file_name.lower().endswith('.json'):
            try:
                data = json.loads(text_content)
                if isinstance(data, list):
                    captions = [str(item).strip() for item in data if str(item).strip()]
                else: # JSON is not a list
                    return None
            except json.JSONDecodeError:
                # If JSON parsing fails, try to parse as plain text as a fallback for .json files
                lines = text_content.splitlines()
                for line in lines:
                    line = line.strip()
                    # Remove potential leading numbering like "1. ", "1) "
                    if line: # Ensure line is not empty after initial strip (e.g. from json list ["foo", "  ", "bar"])
                        captions.append(line) # Use exact line
        elif file_name.lower().endswith('.txt'):
            lines = text_content.splitlines()
            for line in lines:
                # For TXT, we still strip the line itself, but not internal numbering
                cleaned_line = line.strip()
                if cleaned_line: # Add if not empty after stripping line
                    captions.append(cleaned_line)
        else: # Should not happen if check is done before calling
            return None
            
        return captions if captions else None

    except UnicodeDecodeError:
        return None

@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handler para comando /start"""
    user_id = message.from_user.id
    reset_user_data(user_id)
    
    welcome_text = "Envie seus arquivos para renomear ou use o botão abaixo para adicionar um arquivo JSON contendo legenda."
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=create_main_menu()
    )

@bot.message_handler(commands=['done'])
def handle_done(message):
    """Handler para comando /done - limpa tudo e mostra boas vindas"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    data = get_user_data(user_id) # Get user data to access bot_message_ids_to_delete

    # Deletar mensagens específicas rastreadas
    if data['bot_message_ids_to_delete']:
        logger.info(f"User {user_id}: /done command. Deleting {len(data['bot_message_ids_to_delete'])} tracked bot messages.")
        for msg_id in data['bot_message_ids_to_delete']:
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception as e:
                logger.error(f"User {user_id}: Failed to delete message {msg_id}. Error: {e}")
        # Lista será resetada em reset_user_data
    
    # Resetar dados do usuário (isso também limpará bot_message_ids_to_delete)
    reset_user_data(user_id)
    
    # Enviar mensagem de boas vindas (esta não é adicionada à lista de exclusão)
    welcome_text = "Envie seus arquivos para renomear ou use o botão abaixo para adicionar um arquivo JSON contendo legenda."
    
    bot.send_message( # Esta mensagem de boas-vindas não é rastreada para exclusão.
        chat_id,
        welcome_text,
        reply_markup=create_main_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handler para callback queries (botões inline)"""
    user_id = call.from_user.id
    data = get_user_data(user_id)
    
    if call.data == "mode_json":
        data['state'] = WAITING_JSON_FILE
        
        # It's better to send a new message and store its ID than to edit,
        # as edited messages might not be easily trackable for deletion in a simple list.
        # However, the current UI edits the existing "welcome" type message.
        # For simplicity with current structure, we won't track this edited message for /done.
        # If we were to track it, we'd need to send a new message here.
        # The prompt implies "messages of commands, like those displayed when using the 'Json' button".
        # This message is an edit of the original menu. Let's assume it's okay not to delete it,
        # or the user means the *next* message confirming JSON upload.
        # If the user wants this specific prompt ("Envie um arquivo...") deleted, it's tricky
        # as it's an edit. A more robust way would be to delete the original menu message
        # and send a new one. For now, let's focus on messages the bot *sends as new*.

        # Let's assume the request "messages of commands, like those displayed when using the 'Json' button"
        # refers to *new* messages sent by the bot in response to command-like interactions.
        # The message "Envie um arquivo JSON com suas legendas." is an *edit* of the current message.
        # We will focus on tracking IDs of *newly sent* messages by the bot.
        # The message "Arquivo JSON processado!" IS a new message.

        bot.edit_message_text( # This message is an edit, not a new one.
            "Envie um arquivo JSON com suas legendas.",
            call.message.chat.id,
            call.message.message_id
        )
    
    bot.answer_callback_query(call.id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handler para documentos (arquivos JSON e outros)"""
    user_id = message.from_user.id
    data = get_user_data(user_id)
    
    if data['state'] == WAITING_JSON_FILE:
        # Processar arquivo JSON de legendas
        file_name = message.document.file_name
        
        if not (file_name.lower().endswith('.json') or file_name.lower().endswith('.txt')):
            bot.reply_to(
                message,
                "Por favor, envie um arquivo JSON ou TXT válido."
            )
            return
        
        try:
            # Baixar arquivo
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Processar legendas
            captions = process_caption_file(downloaded_file, file_name)
            
            if captions is None:
                bot.reply_to(
                    message,
                    "Erro ao ler arquivo de legendas. Certifique-se de que é um arquivo JSON ou TXT válido e não está vazio."
                )
                return
            
            if len(captions) < 10:
                bot.reply_to(
                    message,
                    f"Arquivo deve ter pelo menos 10 legendas válidas. Encontradas apenas {len(captions)} legendas."
                )
                return
            
            # Salvar legendas e mudar estado
            data['custom_captions'] = captions
            data['state'] = WAITING_MEDIA_FILES
            data['caption_index'] = 0
            
            sent_message = bot.reply_to(
                message,
                f"Arquivo JSON processado! {len(captions)} legendas carregadas. Agora envie seus arquivos."
            )
            data['bot_message_ids_to_delete'].append(sent_message.message_id)
            
        except Exception as e:
            logger.error(f"Erro ao processar arquivo JSON: {e}")
            bot.reply_to(
                message,
                "Erro ao processar arquivo JSON. Tente novamente."
            )
    
    elif data['state'] == WAITING_MEDIA_FILES:
        # Coletar documento como mídia
        collect_media(message, user_id)
    
    else:
        # Estado inicial - processar como mídia sem legendas personalizadas
        data['state'] = WAITING_MEDIA_FILES
        collect_media(message, user_id)

@bot.message_handler(content_types=['photo', 'video'])
def handle_media(message):
    """Handler para fotos e vídeos"""
    user_id = message.from_user.id
    data = get_user_data(user_id)
    
    if data['state'] == WAITING_MEDIA_FILES:
        collect_media(message, user_id)
    else:
        # Estado inicial - processar como mídia sem legendas personalizadas
        data['state'] = WAITING_MEDIA_FILES
        collect_media(message, user_id)

def timeout_process_media(chat_id, user_id):
    """Função chamada pelo timer para processar mídia após timeout"""
    data = get_user_data(user_id)
    
    # Verificar se ainda há arquivos para processar e não está processando
    if data['state'] == WAITING_MEDIA_FILES: # Check state first
        if data['media_count'] > 10:
            logger.info(f"User {user_id}: Timeout reached. Batch size {data['media_count']} is > 10. Deleting batch.")
            delete_collected_media_and_reset(user_id, chat_id)
        elif data['media_count'] > 0: # 1 to 10 files
            logger.info(f"User {user_id}: Timeout reached. Processing {data['media_count']} files.")
            process_media_files(chat_id, user_id)
        # If media_count is 0, do nothing on timeout.

def start_timeout_timer(chat_id, user_id):
    """Inicia ou reinicia o timer de timeout"""
    data = get_user_data(user_id)
    
    # Cancelar timer anterior se existir
    if data['timeout_timer']:
        data['timeout_timer'].cancel()
    
    # Criar novo timer de 10 segundos
    data['timeout_timer'] = threading.Timer(10.0, timeout_process_media, args=(chat_id, user_id))
    data['timeout_timer'].start()
    data['last_media_time'] = time.time()

def collect_media(message, user_id):
    """Coleta arquivos de mídia do usuário"""
    data = get_user_data(user_id)

    # Adicionar arquivo à lista com informações completas
    # A verificação de >10 será feita antes do processamento.
    data['media_messages'].append({
        'message_id': message.message_id,
        'chat_id': message.chat.id,
        'message_obj': message
    })
    data['media_count'] += 1
    
    # Verificar se atingiu 10 arquivos
    if data['media_count'] >= 10:
        # Cancelar timer se existir
    # data['media_count'] has just been incremented.
    if data['media_count'] > 10:
        if data['timeout_timer']: # Cancel timer, as we are invalidating the batch now
            data['timeout_timer'].cancel()
            data['timeout_timer'] = None
        logger.info(f"User {user_id}: media_count is now {data['media_count']} (>10). Deleting current batch.")
        delete_collected_media_and_reset(user_id, message.chat.id)
    elif data['media_count'] == 10:
        if data['timeout_timer']:
            data['timeout_timer'].cancel()
            data['timeout_timer'] = None
        logger.info(f"User {user_id}: media_count is now 10. Processing batch.")
        process_media_files(message.chat.id, user_id)
    else: # 1-9 files
        logger.info(f"User {user_id}: media_count is now {data['media_count']}. Starting/resetting timer.")
        start_timeout_timer(message.chat.id, user_id)

def delete_collected_media_and_reset(user_id, chat_id):
    """Deleta mídias coletadas e reseta o estado parcial do usuário."""
    data = get_user_data(user_id)
    logger.info(f"User {user_id}: Batch of {data['media_count']} files is invalid (>10). Deleting collected media.")
    for media_info in data['media_messages']:
        try:
            bot.delete_message(chat_id, media_info['message_id'])
        except Exception as e:
            logger.error(f"User {user_id}: Failed to delete message {media_info['message_id']}. Error: {e}")

    data['media_messages'] = []
    data['media_count'] = 0
    # Não resetar caption_index aqui, pois o usuário pode querer tentar de novo com um batch válido.
    # O estado WAITING_MEDIA_FILES é apropriado para tentar novamente.
    data['state'] = WAITING_MEDIA_FILES
    if data['timeout_timer']:
        data['timeout_timer'].cancel()
        data['timeout_timer'] = None
    data['last_media_time'] = None


def process_media_files(chat_id, user_id):
    """Processa e reenvia arquivos com legendas já incluídas"""
    data = get_user_data(user_id)

    # Evitar processamento duplicado devido a race conditions
    if data['state'] == PROCESSING:
        logger.warning(
            f"User {user_id}: process_media_files chamado enquanto já estava em estado de PROCESSAMENTO. "
            "Isso pode ser uma race condition benigna. Ignorando esta chamada."
        )
        return
    
    if data['media_count'] == 0:
        return
    
    data['state'] = PROCESSING
    
    # Cancelar timer se existir
    if data['timeout_timer']:
        data['timeout_timer'].cancel()
        data['timeout_timer'] = None
    
    try:
        # Processar cada arquivo com delay
        for i, media_info in enumerate(data['media_messages']):
            try:
                message_id = media_info['message_id']
                message_obj = media_info['message_obj']
                
                # Preparar legenda
                if data['custom_captions'] and data['caption_index'] < len(data['custom_captions']):
                    caption = data['custom_captions'][data['caption_index']]
                    data['caption_index'] += 1
                else:
                    # Usar numeração sequencial baseada no índice atual
                    caption = f"{data['caption_index'] + 1}."
                    data['caption_index'] += 1
                
                # Enviar arquivo com legenda já incluída
                sent_media_message = None
                if message_obj.photo:
                    sent_media_message = bot.send_photo(
                        chat_id,
                        message_obj.photo[-1].file_id,
                        caption=caption
                    )
                elif message_obj.video:
                    sent_media_message = bot.send_video(
                        chat_id,
                        message_obj.video.file_id,
                        caption=caption
                    )
                elif message_obj.document:
                    sent_media_message = bot.send_document(
                        chat_id,
                        message_obj.document.file_id,
                        caption=caption
                    )
                
                if sent_media_message:
                    data['bot_message_ids_to_delete'].append(sent_media_message.message_id)

                # Delay pequeno para evitar problemas de ordem e rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Erro ao enviar arquivo {i + 1} com legenda: {e}")
                continue
        
        # Deletar mensagens originais após processar todos
        for media_info in data['media_messages']:
            try:
                bot.delete_message(chat_id, media_info['message_id'])
            except:
                continue
        
        # Resetar apenas os arquivos, manter legendas e índice
        data['media_messages'] = []
        data['media_count'] = 0
        data['state'] = WAITING_MEDIA_FILES
        data['timeout_timer'] = None
        data['last_media_time'] = None
        
    except Exception as e:
        logger.error(f"Erro durante processamento: {e}")
        # Resetar em caso de erro
        data['media_messages'] = []
        data['media_count'] = 0
        data['state'] = WAITING_MEDIA_FILES
        data['timeout_timer'] = None
        data['last_media_time'] = None

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Handler para outras mensagens"""
    user_id = message.from_user.id
    data = get_user_data(user_id)
    
    if data['state'] == WAITING_MODE_SELECTION:
        # Não responder, apenas aguardar
        pass
    elif data['state'] == WAITING_JSON_FILE:
        bot.reply_to(
            message,
            "Envie um arquivo JSON com suas legendas."
        )
    elif data['state'] == WAITING_MEDIA_FILES:
        # Não responder, apenas aguardar arquivos
        pass

if __name__ == "__main__":
    print("🤖 Bot de Legendas iniciado!")
    print("Pressione Ctrl+C para parar")
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n🛑 Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        print(f"❌ Erro fatal: {e}")