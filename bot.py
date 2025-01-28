import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from config.config import TELEGRAM_TOKEN
from database.mongodb import MongoDB
from services.gemini_service import GeminiService
from services.web_search_service import WebSearchService
import datetime
from PIL import Image
import io
import asyncio
import urllib.parse

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.db = MongoDB()
        self.gemini = GeminiService()
        self.web_search = WebSearchService()
        self.application = None  # Will be set during startup

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id

        # Handle referral
        if context.args and context.args[0].startswith('ref_'):
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != chat_id:  # Prevent self-referral
                await self._handle_referral(referrer_id, chat_id)

        # Save user data
        user_data = {
            'chat_id': chat_id,
            'first_name': user.first_name,
            'username': user.username,
            'joined_at': datetime.datetime.utcnow()
        }
        self.db.save_user(user_data)

        # Request phone number
        button = KeyboardButton("Share Contact", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True)
        
        await update.message.reply_text(
            "Welcome! Please share your contact to complete registration.",
            reply_markup=reply_markup
        )

    async def _handle_referral(self, referrer_id, referred_id):
        """Handle new user coming from referral"""
        try:
            # Save referral
            self.db.save_referral(referrer_id, referred_id)
            
            # Check referral count for rewards
            stats = self.db.get_referral_stats(referrer_id)
            
            # Example reward system
            reward_message = ""
            if stats['total_referrals'] == 5:
                reward_message = "\n\n🎁 Congratulations! You've unlocked premium features for referring 5 users!"
            elif stats['total_referrals'] == 10:
                reward_message = "\n\n🌟 Amazing! You've earned VIP status for referring 10 users!"
            
            # Notify referrer
            message = (
                f"🎉 Someone just joined using your referral link!\n\n"
                f"Total referrals: {stats['total_referrals']}"
                f"{reward_message}\n\n"
                "Keep sharing to earn more rewards!"
            )
            await self.application.bot.send_message(referrer_id, message)
            
        except Exception as e:
            logger.error(f"Error handling referral: {str(e)}")

    async def refer_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /refer command"""
        try:
            user_id = update.effective_user.id
            stats = self.db.get_referral_stats(user_id)
            
            # Get bot info
            bot_info = await context.bot.get_me()
            bot_username = bot_info.username
            
            # Create referral link
            referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
            
            # Create share button
            share_button = InlineKeyboardButton(
                "Share Bot 🔗",
                url=f"https://t.me/share/url?url={urllib.parse.quote(referral_link)}&text={urllib.parse.quote('Check out this amazing AI chatbot!')}"
            )
            reply_markup = InlineKeyboardMarkup([[share_button]])
            
            message = (
                f"🎯 Your Referral Stats:\n"
                f"Total referrals: {stats['total_referrals']}\n\n"
                f"📱 Your referral link:\n{referral_link}\n\n"
                "Share this link with your friends and earn rewards!"
            )
            
            await update.message.reply_text(
                message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in refer command: {str(e)}")
            await update.message.reply_text(
                "Sorry, there was an error generating your referral link. Please try again later."
            )

    async def handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        contact = update.message.contact
        chat_id = update.effective_chat.id
        
        # Update user with phone number
        self.db.save_user({
            'chat_id': chat_id,
            'phone_number': contact.phone_number
        })
        
        await update.message.reply_text(
            "Registration complete! You can now use the bot.\n\n"
            "Type /help to see all available commands and features.\n\n"
            "Quick Start:\n"
            "• /dashboard - View your statistics\n"
            "• /refer - Get your referral link\n"
            "• Send any message to chat with AI\n"
            "• Send any image for analysis"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            chat_id = update.effective_chat.id
            message_text = update.message.text
            
            # Send typing action
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            
            # Get AI response
            response = await self.gemini.get_response(message_text)
            
            # Save chat history
            chat_data = {
                'chat_id': chat_id,
                'user_message': message_text,
                'bot_response': response,
                'timestamp': datetime.datetime.utcnow()
            }
            self.db.save_chat(chat_data)
            
            # Split long responses
            if len(response) > 4096:
                for i in range(0, len(response), 4096):
                    chunk = response[i:i+4096]
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(response)
                
        except Exception as e:
            logger.error(f"Error in handle_message: {str(e)}")
            await update.message.reply_text(
                "I apologize, but I encountered an error processing your message. Please try again later."
            )

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            chat_id = update.effective_chat.id
            photo = update.message.photo[-1]  # Get the largest photo
            
            # Send typing action and keep it active
            typing_task = asyncio.create_task(self._keep_typing(chat_id, context.bot))
            
            try:
                # Download the image
                file = await context.bot.get_file(photo.file_id)
                image_bytes = await file.download_as_bytearray()
                
                # Open and optimize the image
                image = Image.open(io.BytesIO(image_bytes))
                
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Resize if the image is too large
                max_size = 768
                if max(image.size) > max_size:
                    ratio = max_size / max(image.size)
                    new_size = tuple(int(dim * ratio) for dim in image.size)
                    image = image.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert back to bytes with optimization
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
                image_bytes = img_byte_arr.getvalue()
                
                # Analyze image
                analysis = await self.gemini.analyze_image(image_bytes)
                
                # Save file metadata
                file_data = {
                    'chat_id': chat_id,
                    'file_id': photo.file_id,
                    'analysis': analysis,
                    'timestamp': datetime.datetime.utcnow()
                }
                self.db.save_file(file_data)
                
                await update.message.reply_text(f"Image Analysis:\n{analysis}")
                
            finally:
                # Cancel the typing action
                typing_task.cancel()
                
        except Exception as e:
            logger.error(f"Error in handle_image: {str(e)}")
            await update.message.reply_text(
                "I apologize, but I encountered an error processing your image. Please try again later."
            )

    async def _keep_typing(self, chat_id: int, bot):
        """Keep the typing indicator active"""
        try:
            while True:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(5)  # Telegram's typing action expires after ~5 seconds
        except asyncio.CancelledError:
            pass

    async def web_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Please enter your search query:")
        context.user_data['expecting_search'] = True

    async def handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('expecting_search'):
            query = update.message.text
            search_results = await self.web_search.search(query)
            
            response = f"Summary:\n{search_results['summary']}\n\nTop Results:\n"
            response += "\n".join(search_results['links'])
            
            await update.message.reply_text(response)
            context.user_data['expecting_search'] = False

    async def dashboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /dashboard command"""
        try:
            user_id = update.effective_user.id
            
            # Get overall stats
            stats = self.db.get_dashboard_stats()
            if not stats:
                await update.message.reply_text("Error fetching dashboard statistics.")
                return
            
            # Get user-specific stats
            user_stats = self.db.get_user_details(user_id)
            if not user_stats:
                await update.message.reply_text("Error fetching user statistics.")
                return
            
            # Format overall statistics
            dashboard_text = (
                "📊 *Dashboard Statistics*\n\n"
                f"👥 *Total Users:* {stats['total_users']}\n"
                f"💭 *Total Chats:* {stats['total_chats']}\n"
                f"🖼 *Images Analyzed:* {stats['total_images']}\n"
                f"🔗 *Total Referrals:* {stats['total_referrals']}\n"
                f"📈 *Active Users (24h):* {stats['active_users_24h']}\n\n"
                
                "🏆 *Top Referrers*\n"
            )
            
            # Add top referrers
            for idx, referrer in enumerate(stats['top_referrers'], 1):
                dashboard_text += f"{idx}. User {referrer['_id']}: {referrer['count']} referrals\n"
            
            # Add user's personal stats
            dashboard_text += (
                "\n👤 *Your Statistics*\n"
                f"Messages Sent: {user_stats['chat_count']}\n"
                f"Images Analyzed: {user_stats['image_count']}\n"
                f"Referrals Made: {user_stats['referral_stats']['total_referrals']}\n"
            )
            
            # Add user growth chart for last 7 days
            dashboard_text += "\n📈 *User Growth (Last 7 Days)*\n"
            for day in stats['daily_users']:
                dashboard_text += f"{day['_id']}: +{day['count']} users\n"
            
            # Send dashboard with markdown formatting
            await update.message.reply_text(
                dashboard_text,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in dashboard command: {str(e)}")
            await update.message.reply_text(
                "Sorry, there was an error generating the dashboard. Please try again later."
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "🤖 *Available Commands*\n\n"
            "🔹 */start* - Start the bot and register\n"
            "🔹 */help* - Show this help message\n"
            "🔹 */dashboard* - View bot statistics and your analytics\n"
            "🔹 */refer* - Get your referral link and earn rewards\n"
            "🔹 */websearch* - Search the web for information\n\n"
            "📝 *Other Features*\n"
            "• Send any message to chat with AI\n"
            "• Send any image for AI analysis\n\n"
            "💡 *Tips*\n"
            "• Use /dashboard to track your usage\n"
            "• Share your referral link to earn rewards\n"
            "• Images are automatically optimized for analysis"
        )
        
        # Create keyboard with command buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 Dashboard", callback_data="cmd_dashboard"),
                InlineKeyboardButton("🔗 Refer", callback_data="cmd_refer")
            ],
            [
                InlineKeyboardButton("🔍 Web Search", callback_data="cmd_websearch"),
                InlineKeyboardButton("ℹ️ Help", callback_data="cmd_help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()  # Answer the callback query
        
        command_map = {
            'cmd_dashboard': self.dashboard_command,
            'cmd_refer': self.refer_command,
            'cmd_websearch': self.web_search_command,
            'cmd_help': self.help_command
        }
        
        command = command_map.get(query.data)
        if command:
            await command(update, context)

def main():
    try:
        # Create the bot and application
        bot = TelegramBot()
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Store application reference
        bot.application = application

        # Add handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("help", bot.help_command))
        application.add_handler(CommandHandler("refer", bot.refer_command))
        application.add_handler(CommandHandler("websearch", bot.web_search_command))
        application.add_handler(CommandHandler("dashboard", bot.dashboard_command))
        application.add_handler(MessageHandler(filters.CONTACT, bot.handle_contact))
        application.add_handler(MessageHandler(filters.PHOTO, bot.handle_image))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
        application.add_handler(CallbackQueryHandler(bot.button_callback))

        # Add error handler
        application.add_error_handler(
            lambda update, context: logger.error(f"Update {update} caused error {context.error}")
        )

        # Start the bot
        logger.info("Starting bot...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == '__main__':
    main() 