from pymongo import MongoClient
from config.config import MONGODB_URI, DB_NAME
import datetime
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DB_NAME]
        self.users = self.db.users
        self.chats = self.db.chats
        self.files = self.db.files
        self.referrals = self.db.referrals

    def save_user(self, user_data):
        return self.users.update_one(
            {'chat_id': user_data['chat_id']},
            {'$set': user_data},
            upsert=True
        )

    def save_chat(self, chat_data):
        return self.chats.insert_one(chat_data)

    def save_file(self, file_data):
        return self.files.insert_one(file_data)

    def get_user(self, chat_id):
        return self.users.find_one({'chat_id': chat_id})

    def save_referral(self, referrer_id, referred_id):
        """Save a new referral"""
        referral_data = {
            'referrer_id': referrer_id,
            'referred_id': referred_id,
            'timestamp': datetime.datetime.utcnow()
        }
        return self.referrals.insert_one(referral_data)

    def get_referral_count(self, user_id):
        """Get number of successful referrals by a user"""
        return self.referrals.count_documents({'referrer_id': user_id})

    def get_referral_stats(self, user_id):
        """Get detailed referral statistics"""
        total_referrals = self.get_referral_count(user_id)
        recent_referrals = self.referrals.find(
            {'referrer_id': user_id},
            {'referred_id': 1, 'timestamp': 1}
        ).sort('timestamp', -1).limit(5)
        
        return {
            'total_referrals': total_referrals,
            'recent_referrals': list(recent_referrals)
        }

    def get_dashboard_stats(self):
        """Get overall dashboard statistics"""
        try:
            total_users = self.users.count_documents({})
            total_chats = self.chats.count_documents({})
            total_images = self.files.count_documents({})
            total_referrals = self.referrals.count_documents({})
            
            # Get active users in last 24 hours
            last_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            active_users = self.chats.distinct('chat_id', {
                'timestamp': {'$gte': last_24h}
            })
            
            # Get top referrers
            top_referrers = list(self.referrals.aggregate([
                {'$group': {
                    '_id': '$referrer_id',
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': 5}
            ]))
            
            # Get user growth over last 7 days
            seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            daily_users = list(self.users.aggregate([
                {'$match': {'joined_at': {'$gte': seven_days_ago}}},
                {'$group': {
                    '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$joined_at'}},
                    'count': {'$sum': 1}
                }},
                {'$sort': {'_id': 1}}
            ]))
            
            return {
                'total_users': total_users,
                'total_chats': total_chats,
                'total_images': total_images,
                'total_referrals': total_referrals,
                'active_users_24h': len(active_users),
                'top_referrers': top_referrers,
                'daily_users': daily_users
            }
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}")
            return None

    def get_user_details(self, user_id):
        """Get detailed stats for a specific user"""
        try:
            user = self.users.find_one({'chat_id': user_id})
            if not user:
                return None
                
            # Get user's chat count
            chat_count = self.chats.count_documents({'chat_id': user_id})
            
            # Get user's image analysis count
            image_count = self.files.count_documents({'chat_id': user_id})
            
            # Get referral stats
            referral_stats = self.get_referral_stats(user_id)
            
            return {
                'user': user,
                'chat_count': chat_count,
                'image_count': image_count,
                'referral_stats': referral_stats
            }
        except Exception as e:
            logger.error(f"Error getting user details: {str(e)}")
            return None 